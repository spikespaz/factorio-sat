import argparse, sys, json
from util import *
import numpy as np

import solver

def ensure_loop_length(grid: solver.Grid, edge_mode: EdgeModeType):
    for y in range(grid.height):
        for x in range(grid.width):
            tile_a = grid.get_tile_instance(x, y)

            for direction in range(4):
                tile_b = grid.get_tile_instance_offset(x, y, *direction_to_vec(direction), edge_mode)

                if tile_b in (BLOCKED_TILE, IGNORED_TILE):
                    continue

                if direction % 2 == 0:
                    colour_a = tile_a.colour_ux
                    colour_b = tile_b.colour_ux
                else:
                    colour_a = tile_a.colour_uy
                    colour_b = tile_b.colour_uy

                grid.clauses += implies([tile_a.output_direction[direction]], increment_number(tile_a.colour, tile_b.colour))
                grid.clauses += implies([tile_a.input_direction[direction], *invert_components(tile_a.output_direction)], increment_number(tile_a.colour, colour_b))

                for i in range(len(tile_a.colour)):
                    grid.clauses += implies([*invert_components(tile_b.input_direction), tile_b.output_direction[direction]], variables_same(colour_a[i], tile_b.colour[i]))
                    grid.clauses += implies([tile_a.underground[direction], tile_b.underground[direction]], variables_same(colour_a[i], colour_b[i]))

def is_power_of_two(value):
    return not (value & (value - 1))          

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Creates a stream of blocks of random belts')
    parser.add_argument('width', type=int, help='Block width')
    parser.add_argument('height', type=int, help='Block height')
    parser.add_argument('--tile', action='store_true', help='Makes output blocks tilable')
    parser.add_argument('--allow-empty', action='store_true', help='Allow empty tiles')
    parser.add_argument('--underground-length', type=int, default=4, help='Maximum length of underground section (excludes ends)')
    parser.add_argument('--all', action='store_true', help='Produce all blocks')
    parser.add_argument('--label', type=str, help='Output blueprint label')
    parser.add_argument('--solver', type=str, default='Glucose3', help='Backend SAT solver to use')
    parser.add_argument('--single-loop', action='store_true', help='Prevent multiple loops')
    parser.add_argument('--output', type=argparse.FileType('w'), nargs='?', help='Output file, if no file provided then results are sent to standard out')
    args = parser.parse_args()


    if args.allow_empty and args.single_loop:
        raise RuntimeError('Incompatible options: allow-empty + single-loop')

    if args.single_loop and not is_power_of_two(args.width * args.height):
        raise RuntimeError('Cannot create single loop if width*height is not power of two')

    if args.underground_length < 0:
        raise RuntimeError('Underground length cannot be negative')
    
    grid = solver.Grid(args.width, args.height, args.width * args.height if args.single_loop else 1)

    edge_mode = EDGE_MODE_TILE if args.tile else EDGE_MODE_BLOCK

    grid.prevent_intersection(edge_mode)
    grid.prevent_bad_undergrounding(edge_mode)

    grid.prevent_small_loops()
    
    if args.underground_length > 0:
        grid.prevent_empty_along_underground(args.underground_length, edge_mode)
        grid.set_maximum_underground_length(args.underground_length, edge_mode)


    if args.single_loop:
        ensure_loop_length(grid, edge_mode)
        grid.clauses += set_number(0, grid.get_tile_instance(0,0).colour)

    for x in range(grid.width):
        for y in range(grid.height):
            tile = grid.get_tile_instance(x, y)
            if not args.allow_empty:
                grid.clauses.append(tile.all_direction) # Ban Empty

            if args.underground_length == 0: # Ban underground
                for direction in range(4):
                    grid.clauses.append([-tile.underground[direction]])

            grid.clauses += set_number(0, tile.is_splitter) # Ban splitters
    
    if args.output is not None:
        with args.output:
            for solution in grid.itersolve(True, args.solver):
                json.dump(solution.tolist(), args.output)
                args.output.write('\n')
                if not args.all:
                    break
    else:
        for i, solution in enumerate(grid.itersolve(True, args.solver)):
            print(json.dumps(solution.tolist()))

            if i == 0:
                sys.stdout.flush() # Push the first one out as fast a possible

            if not args.all:
                break