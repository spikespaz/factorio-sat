from typing import *

import traceback, math, collections
from os.path import basename

import numpy as np

from pysat.solvers import Solver
from pysat.formula import CNF


#from pycryptosat import Solver as PyCryptoSolver


class BaseTile:
    def __init__(self, input_direction=None, output_direction=None):
        self.input_direction = input_direction
        self.output_direction = output_direction

class Belt(BaseTile):
    def __init__(self, input_direction, output_direction):
        assert (input_direction - output_direction) % 4 != 2
        super().__init__(input_direction, output_direction)

    def __eq__(self, other):
        if self is other:
            return True
        if not isinstance(other, Belt):
            return False

        return self.input_direction == other.input_direction and self.output_direction == other.output_direction

    def __hash__(self):
        return hash((self.input_direction, self.output_direction))

    def __str__(self):
        return 'Belt({}, {})'.format(self.input_direction, self.output_direction)
    __repr__ = __str__

class UndergroundBelt(BaseTile):
    def __init__(self, direction, is_input):
        self.direction = direction
        self.is_input = is_input

        if is_input:
            super().__init__(direction, None)
        else:
            super().__init__(None, direction)
    
    def __eq__(self, other):
        if self is other:
            return True
        if not isinstance(other, UndergroundBelt):
            return False

        return self.direction == other.direction and self.is_input == other.is_input

    def __hash__(self):
        return hash((self.direction, self.is_input))

    def __str__(self):
        return 'UndergroundBelt({}, {})'.format(self.direction, self.is_input)
    __repr__ = __str__

class Splitter(BaseTile):
    def __init__(self, direction, side):
        self.direction = direction
        self.side = side # 0 = left, 1 = right

        super().__init__(direction, direction)

    def __eq__(self, other):
        if self is other:
            return True
        if not isinstance(other, Splitter):
            return False

        return self.direction == other.direction and self.side == other.side

    def __hash__(self):
        return hash((self.direction, self.side))

    def __str__(self):
        return 'Splitter({}, {})'.format(self.direction, self.side)
    __repr__ = __str__

class Inserter(BaseTile):
    def __init__(self, direction, type):
        self.direction = direction
        self.type = type # 0 -> Normal, 1 -> Long

        super().__init__()

    def __eq__(self, other):
        if self is other:
            return True
        if not isinstance(other, Inserter):
            return False

        return self.direction == other.direction and self.type == other.type
    
    def __hash__(self):
        return hash((self.direction, self.type))

    def __str__(self):
        return 'Inserter({}, {})'.format(self.direction, self.type)
    __repr__ = __str__

class AssemblingMachine(BaseTile):
    def __init__(self, x, y):
        self.x = x
        self.y = y
        super().__init__()

    def __eq__(self, other):
        if self is other:
            return True
        if not isinstance(other, AssemblingMachine):
            return False
        
        return self.x == other.x and self.y == other.y
    
    def __hash__(self):
        return hash((self.x, self.y))
    
    def __str__(self):
        return 'AssemblingMachine({}, {})'.format(self.x, self.y)
    __repr__ = __str__

VariableType = int
ClauseType = List[VariableType]
ClauseList = List[ClauseType]
AllocatorType = Callable[[], int]

def get_stack(): # Doesn't include caller
    result = []
    for entry in traceback.extract_stack()[:-2]:
        result.append((entry.filename, entry.lineno))
    return tuple(result)

class StackTracingList(list):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.traces = collections.defaultdict(lambda: 0)

    def __iadd__(self, other):
        self.traces[get_stack()] += len(other)
        return super().__iadd__(other)

    def append(self, value):
        self.traces[get_stack()] += 1
        super().append(value)

    def profile(self):
        longest_file = max(len(basename(file)) for stack in self.traces for file, _ in stack)
        longest_lineno = max(lineno for stack in self.traces for _, lineno in stack)
        deepest_stack = max(len(stack) for stack in self.traces)

        format = ('{:>' + str(longest_file) + '}:{:<' + str(len(str(longest_lineno))) + '}').format

        trace_length = len(format('','')) * deepest_stack + 2 * (deepest_stack-1)

        for stack, count in sorted(self.traces.items(), key=lambda v: v[1], reverse=True):
            trace = ', '.join(format(basename(file), lineno) for file, lineno in stack)
            print(trace + ' ' * (trace_length - len(trace)) + ' - ' + str(count))

EDGE_MODE_IGNORE = 'EDGE_IGNORE'
EDGE_MODE_BLOCK  = 'EDGE_BLOCK'
EDGE_MODE_TILE   = 'EDGE_TILE'
IGNORED_TILE     = 'TILE_IGNORE'
BLOCKED_TILE     = 'TILE_BLOCK'

EdgeModeEnumType = Literal['EDGE_IGNORE', 'EDGE_BLOCK', 'EDGE_TILE']
EdgeModeType = Union[Tuple[EdgeModeEnumType, EdgeModeEnumType], EdgeModeEnumType]
OffsetTileType = Union[Literal['TILE_IGNORE', 'TILE_BLOCK'], 'TileTemplate']

def add_numbers(input_a: List[VariableType], input_b: List[VariableType], output: List[VariableType], allocator: AllocatorType, carry_in: Optional[VariableType]=None, allow_overflow=False) -> ClauseList:
    assert len(input_a) == len(input_b)
    assert len(output) in (len(input_a), len(input_a) + 1)

    clauses = []
    for in_a, in_b, out in zip(input_a, input_b, output):
        carry_out = allocator()
        if carry_in is None:
            clauses += [
                [-in_a, -in_b, carry_out],
                [in_a, -carry_out],
                [in_b, -carry_out],

                [ in_a,  in_b, -out],
                [-in_a,  in_b,  out],
                [ in_a, -in_b,  out],
                [-in_a, -in_b, -out],   
            ]
        else:
            clauses += [
                [-in_a, -in_b,     carry_out],
                [-in_a, -carry_in, carry_out],
                [-in_b, -carry_in, carry_out],

                [in_a, in_b,     -carry_out],
                [in_a, carry_in, -carry_out],
                [in_b, carry_in, -carry_out],

                [ in_a,  in_b,  carry_in, -out],
                [-in_a,  in_b,  carry_in,  out],
                [ in_a, -in_b,  carry_in,  out],
                [-in_a, -in_b,  carry_in, -out],
                [ in_a,  in_b, -carry_in,  out],
                [-in_a,  in_b, -carry_in, -out],
                [ in_a, -in_b, -carry_in, -out],
                [-in_a, -in_b, -carry_in,  out],      
            ]

        carry_in = carry_out

    if len(output) > len(input_a):
        clauses += variables_same(carry_in, output[-1])
    elif not allow_overflow:
        clauses += [[-carry_in]]
    return clauses

def sum_numbers(numbers: List[List[VariableType]], output: List[VariableType], allocator: AllocatorType, allow_overflow=False) -> ClauseList:
    assert len(numbers) > 1

    size = len(numbers[0])
    assert all(len(number) == size for number in numbers) and size == len(output)

    clauses = []

    number_in = numbers[0]
    for i, number in enumerate(numbers[1:]):
        if i == len(numbers) - 2:
            number_out = output
        else:
            number_out = [allocator() for _ in range(size)]
        
        clauses += add_numbers(number_in, number, number_out, allocator, allow_overflow=allow_overflow)

        number_in = number_out

    return clauses

def increment_number(input: List[VariableType], output: List[VariableType]):
    assert len(input) == len(output)
    assert len(input) > 0

    clauses = []
    for i, (in_var, out_var) in enumerate(zip(input, output)):
        clauses += implies(input[:i], variables_different(in_var, out_var))

        for var in input[:i]:
            clauses += implies([-var], variables_same(in_var, out_var))
    return clauses

def get_popcount(bits: List[VariableType], output: List[VariableType], allocator: AllocatorType) -> ClauseList:
    assert bin_length(len(bits) + 1) == len(output)
    assert len(bits) > 1

    clauses = []
    if len(bits) <= 3:
        carry_in = bits[2] if len(bits) == 3 else None
        clauses += add_numbers([bits[0]], [bits[1]], output, allocator, carry_in)
    else:
        carry_in = bits[-1] if len(bits) % 2 != 0 else None
        sub_size = len(bits) // 2

        output_a = [allocator() for _ in range(len(output) - 1)]
        output_b = [allocator() for _ in range(len(output) - 1)]

        clauses += get_popcount(bits[:sub_size], output_a, allocator)
        clauses += get_popcount(bits[sub_size:(2*sub_size)], output_b, allocator)
        clauses += add_numbers(output_a, output_b, output, allocator, carry_in)

    return clauses

def read_number(bits: List[bool], signed=False):
    result = 0
    for i, bit in enumerate(bits):
        if bit:
            result |= 1 << i

    if signed:
        assert len(bits) > 1
        if bits[-1]: # Two's complement
            result = result - (1 << len(bits))

    return result

def direction_to_vec(direction: int) -> Tuple[int, int]:
    return [(1,0), (0,-1), (-1,0), (0,1)][direction]

def bin_length(value: int):
    return math.ceil(math.log2(value))

def set_variable(var: VariableType, value: bool) -> VariableType:
    if value:
        return var
    else:
        return -var

def set_number(value: int, variables: List[VariableType]) -> ClauseList:
    assert value < (1 << len(variables))

    clauses = []
    for var, bit in zip(variables, get_bits(value, len(variables))):
        clauses.append([set_variable(var, bit)])
    return clauses

def set_numbers_equal(number_a: List[VariableType], number_b: List[VariableType], allow_different_lengths: bool=False) -> ClauseList:
    clauses = []

    if allow_different_lengths:
        clauses += set_number(0, number_a[len(number_b):])
        clauses += set_number(0, number_b[len(number_a):])
    else:
        assert len(number_a) == len(number_b)
    
    for var_a, var_b in zip(number_a, number_b):
        clauses += variables_same(var_a, var_b)
    return clauses

def set_not_number(value: int, variables: List[VariableType]) -> ClauseType:
    return [-var[0] for var in set_number(value, variables)]


def invert_number(input: List[VariableType], output: List[VariableType], allocator: AllocatorType):
    assert len(input) == len(output)

    clauses = []

    carry_in = None
    for i, (var_a, var_b) in enumerate(zip(input, output)):
        if i == len(input) - 1:
            carry_out = None
        else:
            carry_out = allocator()
        
        if carry_in is None:
            clauses += variables_same(var_a, var_b)
            if carry_out is not None:
                clauses += [
                    [-var_a, -var_b, carry_out],

                    [var_a, -carry_out],
                    [var_b, -carry_out],
                ]
        else:
            clauses += [
                [-var_a, -var_b, -carry_in],

                [-var_a, +var_b, +carry_in],
                [+var_a, -var_b, +carry_in],
                [+var_a, +var_b, -carry_in],
            ]

            if carry_out is not None:
                clauses += [
                    [-var_a, -var_b,    carry_out],
                    [-var_a, -carry_in, carry_out],
                    [-var_b, -carry_in, carry_out],

                    [var_a, var_b,    -carry_out],
                    [var_a, carry_in, -carry_out],
                    [var_b, carry_in, -carry_out],
                ]
        carry_in = carry_out

    clauses.append(input[:-1] + [-input[-1]])

    return clauses

def get_bits(value: int, total_bits: int) -> Generator[bool, None, None]:
    # Result is little-endian
    for bit in range(total_bits):
        yield bool(value & (1<<bit))

def implies(condition: List[VariableType], consequences: ClauseList) -> ClauseList:
    # If all the input variables are the correct value then the consequences must be satisfied
    inverse_condition = [-var for var in condition]
    return [inverse_condition + consequence for consequence in consequences]

def variables_different(var_a: VariableType, var_b: VariableType) -> ClauseList:
    return [[var_a, var_b], [-var_a, -var_b]]

def variables_same(var_a: VariableType, var_b: VariableType) -> ClauseList:
    return [[-var_a, var_b], [var_a, -var_b]]

def invert_components(clause: ClauseType) -> ClauseType:
    # Converts c0 OR c1 OR c2 OR ... to NOT (c0 AND c1 AND c2 AND ...)
    return [-var for var in clause]

def product(values):
    result = 1
    for value in values:
        result *= value
    return result

T = TypeVar('T')
def combinations(items: List[T], size: int) -> Generator[List[T], None, None]:
    if size == 0:
        yield []
    if len(items) < size:
        return
    for i, item in enumerate(items):
        for sub_combination in combinations(items[i+1:], size-1):
            yield [item] + sub_combination

class TileTemplate:
    def __init__(self, template: Dict[str, str]):
        self._template = dict(((key, tuple(val.split(' '))) for key, val in template.items()))
        acc = 0

        reached = set()
        for name, item_type in self._template.items():
            if item_type == ('bool',):
                acc += 1
            elif item_type[0] in ('arr', 'num', 'signed_num', 'one_hot'):
                sizes = [int(v) for v in item_type[1:]]
                assert all(size >= 0 for size in sizes)
                acc += product(sizes)
            elif item_type[0] == 'alias':
                for sub_name in item_type[1:]:
                    if sub_name[0] == '-':
                        sub_name = sub_name[1:]
                    if sub_name not in template:
                        raise ValueError('Alias argument "{}" not in template'.format(sub_name))
                    if sub_name not in reached:
                        raise ValueError('Alias argument "{}" reached in alias before declaration'.format(sub_name))
            else:
                raise ValueError('Invalid template type "{}"'.format(' '.join(item_type)))
            reached.add(name)
        self.size = acc

        self.tile_type = collections.namedtuple('TileInstance', self._template.keys(), rename=True)

    def instantiate(self, index: int):
        assert index >= 0
        acc = index * self.size + 1

        members = {}
        for name, item_type in self._template.items():
            if item_type == ('bool',):
                members[name] = acc
                acc += 1
            elif item_type[0] in ('arr', 'num', 'signed_num', 'one_hot'):
                sizes = [int(v) for v in item_type[1:]]
                def recurse(sizes):
                    nonlocal acc
                    if len(sizes) == 1:
                        result = list(range(acc, acc+sizes[0]))
                        acc += sizes[0]
                    else:
                        result = []
                        for _ in range(sizes[0]):
                            result.append(recurse(sizes[1:]))
                    return result
                members[name] = recurse(sizes)

        def invert(val):
            return (-np.array(val)).tolist()

        for name, item_type in self._template.items():
            if item_type[0] == 'alias':
                if len(item_type) == 2:
                    key = item_type[1]
                    if key[0] == '-':
                        inverted = True
                        key = key[1:]
                    else:
                        inverted = False
                    
                    value = members[key[1]]
                    
                    if inverted:
                        value = invert(value)
                    members[name] = value
                else:
                    combined = []
                    for key in item_type[1:]:
                        if key[0] == '-':
                            inverted = True
                            key = key[1:]
                        else:
                            inverted = False
                        value = members[key]

                        if isinstance(value, list) and len(value) > 0 and isinstance(value[0], list):
                            raise NotImplementedError('Cannot compose multi-dimensional element into alias')

                        if inverted:
                            value = invert(value)

                        if isinstance(value, int):
                            combined.append(value)
                        else:
                            combined += value
                    members[name] = combined
        return self.tile_type(**members)

    def merge(self, other):
        result_template = dict((key, ' '.join(val)) for key, val in self._template.items())
        for name, item_type in other._template.items():
            item_type = ' '.join(item_type)
            if name in result_template and result_template[name] != item_type:
                raise ValueError('Incompatible tile templates for merge')
            result_template[name] = item_type

        return TileTemplate(result_template)

    def parse(self, variables: List[bool]):
        assert len(variables) % self.size == 0

        result = []
        for i in range(0, len(variables), self.size):
            entry = {}
            for name, item_type in self._template.items():
                if item_type == ('bool',):
                    entry[name] = variables[i]
                    i += 1
                elif item_type[0] in ('arr', 'num', 'signed_num', 'one_hot'):
                    sizes = [int(v) for v in item_type[1:]]
                    arr = np.array(variables[i:(i + product(sizes))])

                    if item_type[0] == 'arr':
                        arr = arr.reshape(sizes)
                    elif item_type[0] in ('num', 'signed_num'):
                        if sizes[-1] == 0:
                            arr = np.zeros(sizes[:-1], dtype=int)
                        else:
                            is_signed = item_type[0] == 'signed_num'
                            arr = np.array([read_number(value, is_signed) for value in arr.reshape((-1, sizes[-1]))])
                            arr = arr.reshape(sizes[:-1])
                    elif item_type[0] == 'one_hot':
                        if sizes[-1] == 0:
                            arr = np.full(sizes[:-1], None)
                        else:
                            temp = []
                            for value in arr.reshape((-1, sizes[-1])):
                                try:
                                    temp.append(value.tolist().index(True))
                                except ValueError:
                                    temp.append(None)
                            arr = np.array(temp, dtype=object).reshape(sizes[:-1])
                    else:
                        assert False
                    entry[name] = arr.tolist()
                    i += product(sizes)
            result.append(entry)
        return np.array(result)

    def initial_clauses(self, indices):
        clauses = []
        for i in indices:
            tile = self.instantiate(i)._asdict()

            for name, item_type in self._template.items():
                if item_type[0] == 'one_hot':
                    entry = np.array(tile[name])

                    #clauses += quadratic_amo()
        return clauses

def expand_edge_mode(edge_mode: EdgeModeType) -> Tuple[EdgeModeEnumType, EdgeModeEnumType]:
    if isinstance(edge_mode, str):
        return edge_mode, edge_mode
    else:
        return edge_mode

class BaseGrid:
    def __init__(self, template: TileTemplate, width: int, height: int):
        assert width > 0 and height > 0
        self.template = template
        self.width = width
        self.height = height

        self.extra_variables = 0
        self.clauses: List[ClauseType] = []

        #self.clauses += template.initial_clauses(range(self.width * self.height))

    @property
    def total_variables(self):
        return self.width * self.height * self.template.size

    @property
    def tile_size(self):
        return self.template.size

    def iterate_tiles(self):
        for x in range(self.width):
            for y in range(self.height):
                yield self.get_tile_instance(x, y)

    def allocate_variable(self):
        result = 1 + self.total_variables + self.extra_variables
        self.extra_variables += 1
        return result

    def get_tile_instance(self, x: int, y: int):
        assert x >= 0 and y >= 0 and x < self.width and y < self.height
        return self.template.instantiate(y * self.width + x)

    def get_tile_instance_offset(self, x: int, y: int, dx: int, dy: int, edge_mode: EdgeModeType) -> OffsetTileType:
        edge_mode = expand_edge_mode(edge_mode)
        assert all(mode in (EDGE_MODE_IGNORE, EDGE_MODE_BLOCK, EDGE_MODE_TILE) for mode in edge_mode)
        
        pos = [x + dx, y + dy]
        size = self.width, self.height

        is_ignored = False
        for i in range(2):
            if pos[i] < 0 or pos[i] >= size[i]:
                if edge_mode[i] == EDGE_MODE_TILE:
                    pos[i] = pos[i] % size[i]
                elif edge_mode[i] == EDGE_MODE_BLOCK:
                    return BLOCKED_TILE
                elif edge_mode[i] == EDGE_MODE_IGNORE:
                    is_ignored = True
                else:
                    assert False
        
        if is_ignored:
            return IGNORED_TILE

        return self.get_tile_instance(*pos)

    def parse_solution(self, solution):
        variables = [False] * self.total_variables

        for item in solution:
            if item > 0 and item <= len(variables):
                variables[item-1] = True
        return np.array(self.template.parse(variables)).reshape((self.height, self.width)).T    

    def check(self, solver='g3'):
        with Solver(name=solver, bootstrap_with=self.clauses) as s:
            return s.solve()
    
    def solve(self, solver='g3'):
        if solver == 'cryptosat':
            s = PyCryptoSolver()
            satisfiable, solution = s.solve()
            if not satisfiable:
                return None
            
            variables = solution[1:(self.total_variables + 1)]
            return np.array(self.template.parse(variables)).reshape((self.height, self.width)).T    
        else:
            with Solver(name=solver, bootstrap_with=self.clauses) as s:
                if s.solve():
                    return self.parse_solution(s.get_model())
                else:
                    return None

    def itersolve(self, important_variables=set(), solver='g3'):
        if solver == 'cryptosat':
            s = PyCryptoSolver()
            s.add_clauses(self.clauses)
            while True:
                satisfiable, solution = s.solve()
                if not satisfiable:
                    break
                
                variables = solution[1:(self.total_variables + 1)]
                yield np.array(self.template.parse(variables)).reshape((self.height, self.width)).T    

                s.add_clause([set_variable(var, not solution[var]) for var in important_variables])
        else:

            with Solver(name=solver, bootstrap_with=self.clauses) as s:
                while s.solve():
                    solution = s.get_model()
                    yield self.parse_solution(solution)
                    
                    s.add_clause([-var for var in solution if abs(var) in important_variables])

    def write(self, filename, comments=None):
        cnf = CNF(from_clauses=self.clauses)
        cnf.to_file(filename, comments)