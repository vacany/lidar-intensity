import math

import numpy as np

from . import io, query


def failed_result(snapshots, dataitems, index, args):
    if args.delete_originals:
        if args.needs_all:
            io.delete_orig_files(snapshots, args)
        else:
            io.delete_orig_files([snapshots[index]], args)
    if args.delete_invalid:
        if args.needs_all:
            io.delete_orig_files(snapshots, args)
            if dataitems is not None:
                io.delete_created_files(dataitems, args)
        else:
            snapshot = snapshots[index]
            io.delete_orig_files([snapshot], args)
            if dataitems is not None:
                dataitem = dataitems[index]
                io.delete_created_files([dataitem], args)


def process_snapshot(snapshot, prev, args):
    dataitem = io.Snapshot(snapshot)
    if not dataitem.load_rgb(args):
        return False, dataitem
    if not dataitem.load_depth(args):
        return False, dataitem
    if not dataitem.load_stencil(args):
        return False, dataitem
    if not dataitem.load_meta(args):
        return False, dataitem
    if prev is not None and np.all(dataitem.depth == prev.depth) and np.all(dataitem.stencil == prev.stencil):
        return False, dataitem
    return True, dataitem


def process_scene(scene_id, run_id, args):
    args.cursor.execute(query.SNAPSHOTS, (run_id, scene_id))
    snapshots = args.cursor.fetchall()
    if len(snapshots) != args.num_cameras:
        for i in range(len(snapshots)):
            failed_result(snapshots, None, i, args)
        if args.verbose:
            print('There are not enough snapshots for the scene!')
        if args.needs_all:
            return
    dataitems = []
    prev = None
    for i, snapshot in enumerate(snapshots):
        result, prev = process_snapshot(snapshot, prev, args)
        if not result:
            failed_result(snapshots, None, i, args)
            if args.needs_all:
                return
            continue
        dataitems.append(prev)

    started_img_id = args.img_id
    for i, dataitem in enumerate(dataitems):
        result = dataitem.save_snapshot(args)
        if not result:
            failed_result(snapshots, dataitems, i, args)
            if args.needs_all:
                args.img_id = started_img_id
                return
            continue
        args.img_id += 1


def get_runs(args):
    args.cursor.execute(query.RUNS)
    run_ids = args.cursor.fetchall()
    run_ids = set([result.run_id for result in run_ids])
    if args.all_runs:
        args.runs = run_ids
    else:
        runs = run_ids & set(args.runs)
        unused = set(args.runs) - runs
        if unused and args.verbose:
            print(f'There were some run ids, which were specified, but not found in the database!')
            print(f'The IDs are {unused}')
        args.runs = runs
    if args.verbose:
        print(f'Used run ids are {args.runs}')


def process_run(run_id, args):
    args.current_run_id = run_id
    reset = False
    if args.num_cameras is None:
        args.cursor.execute(query.CAMS, (run_id,))
        args.num_cameras = len(args.cursor.fetchall())
        reset = True
        if args.verbose:
            print(f'There are {args.num_cameras} cameras for run {run_id}')
    scene_ids = get_scene_ids(args.cursor, run_id)
    if args.verbose:
        print(f'There are {len(scene_ids)} scenes for run {run_id}')
    args.cursor.execute(query.SNAPSHOTS_NUM, (run_id,))
    num_snapshots = args.cursor.fetchone().count
    args.format_width = math.ceil(math.log10(num_snapshots + 1))
    if args.verbose:
        print(f'There are {num_snapshots} snaphots for run {run_id}')
    args.img_id = 0
    for scene_id in scene_ids:
        process_scene(scene_id, run_id, args)
    if reset:
        args.num_cameras = None
    if (args.img_id == 0 and args.delete_invalid) or args.delete_originals:
        args.cursor.execute(query.DELETE_RUN, (run_id,))


def get_scene_ids(cursor, run_id):
    results = []
    last_scene_id = None
    cursor.execute(query.SCENE_IDS, (run_id,))
    for result in cursor:
        if result.scene_id == last_scene_id:
            continue
        results.append(result.scene_id)
        last_scene_id = result.scene_id
    return results