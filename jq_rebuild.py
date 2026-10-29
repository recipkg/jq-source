"""Initial jq-compatible filter interpreter, generated from the Recipkg recipe.

This is deliberately incomplete. Reject unsupported operations explicitly.
"""
import codecs
import copy
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN
import functools
import json
import math
from pathlib import Path
import re
import sys


class CompileError(Exception):
    pass


class RuntimeErrorJq(Exception):
    pass


class JqNumber:
    """A decimal literal that keeps its value and display precision."""

    def __init__(self, text):
        try:
            self.decimal = Decimal(text)
        except InvalidOperation as exc:
            raise RuntimeErrorJq('invalid numeric literal') from exc

    @classmethod
    def from_decimal(cls, value):
        result = cls.__new__(cls)
        result.decimal = value
        return result

    def negate(self):
        value = self.decimal.copy_abs() if self.decimal.is_zero() else self.decimal.copy_negate()
        return self.from_decimal(value)


def is_number(value):
    return isinstance(value, JqNumber) or type(value) in (int, float)


def as_float(value):
    if not isinstance(value, JqNumber):
        return float(value)
    decimal = value.decimal
    if decimal.is_zero() or decimal.adjusted() < -325 or decimal.adjusted() > 309:
        return float(decimal)
    return float(Context(prec=17, rounding=ROUND_HALF_EVEN).create_decimal(decimal))


def as_index(value):
    if not is_number(value):
        return None
    number = as_float(value)
    if not math.isfinite(number):
        return None
    return int(number)


def format_float(value):
    if math.isnan(value):
        return 'null'
    if math.isinf(value):
        value = math.copysign(sys.float_info.max, value)
    decimal = Decimal(repr(value))
    if decimal.is_zero():
        return '-0' if decimal.is_signed() else '0'
    sign, raw_digits, exponent = decimal.as_tuple()
    digits = ''.join(str(digit) for digit in raw_digits).lstrip('0')
    digits = digits.rstrip('0')
    magnitude = decimal.adjusted()
    if -4 <= magnitude < len(digits) + 15:
        result = format(decimal, 'f')
        if '.' in result:
            result = result.rstrip('0').rstrip('.')
        return result
    mantissa = digits[0] + ('.' + digits[1:] if len(digits) > 1 else '')
    sign_text = '-' if sign else ''
    exponent_text = ('+' if magnitude >= 0 else '-') + f'{abs(magnitude):02d}'
    return sign_text + mantissa + 'e' + exponent_text


def dump_json(value, compact=False, depth=0):
    if isinstance(value, JqNumber):
        return str(value.decimal)
    if isinstance(value, float):
        return format_float(value)
    if value is None or isinstance(value, (bool, int, str)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, dict)):
        is_dict = isinstance(value, dict)
        items = list(value.items()) if is_dict else value
        if not items:
            return '{}' if is_dict else '[]'
        rendered = []
        for item in items:
            if is_dict:
                key, child = item
                text = json.dumps(key, ensure_ascii=False) + (':' if compact else ': ')
                text += dump_json(child, compact, depth + 1)
            else:
                text = dump_json(item, compact, depth + 1)
            rendered.append(text)
        left, right = ('{', '}') if is_dict else ('[', ']')
        if compact:
            return left + ','.join(rendered) + right
        indentation = '  ' * (depth + 1)
        return left + '\n' + indentation + (',\n' + indentation).join(rendered) + '\n' + '  ' * depth + right
    raise RuntimeErrorJq('unsupported JSON value')


TOKEN = re.compile(
    r'\s*(?:(?P<string>"(?:\\.|[^"\\])*")|(?P<number>(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)'
    r'|(?P<variable>\$[A-Za-z_][A-Za-z_0-9]*)|(?P<word>[A-Za-z_][A-Za-z_0-9]*)'
    r'|(?P<op>==|!=|>=|<=|//|\|=|[.\[\]{}:,;()|+*<>=?-]))'
)


class Parser:
    def __init__(self, text):
        self.tokens = []
        self.positions = []
        offset = 0
        while text:
            if not text.strip():
                break
            match = TOKEN.match(text)
            if not match:
                raise CompileError('unsupported or invalid syntax near ' + repr(text[:20]))
            self.tokens.append((match.lastgroup, match.group(match.lastgroup)))
            self.positions.append((offset + match.start(match.lastgroup),
                                   offset + match.end(match.lastgroup)))
            offset += match.end()
            text = text[match.end():]
        self.pos = 0

    def peek(self, value=None):
        if self.pos >= len(self.tokens):
            return False if value is not None else None
        return self.tokens[self.pos][1] == value if value is not None else self.tokens[self.pos]

    def take(self, value=None):
        token = self.peek()
        if token is None or (value is not None and token[1] != value):
            raise CompileError('expected ' + repr(value))
        self.pos += 1
        return token

    def parse(self):
        node = self.pipe()
        if self.peek() is not None:
            raise CompileError('unexpected token ' + self.peek()[1])
        return node

    def pipe(self):
        if self.peek('def'):
            self.take('def')
            name = self.take()
            if name[0] != 'word':
                raise CompileError('expected function name')
            parameters = []
            if self.peek('('):
                self.take('(')
                while True:
                    parameter = self.take()
                    if parameter[0] not in ('word', 'variable'):
                        raise CompileError('expected function parameter')
                    parameters.append((parameter[0], parameter[1].lstrip('$')))
                    if not self.peek(';'):
                        break
                    self.take(';')
                self.take(')')
            self.take(':')
            body = self.pipe()
            self.take(';')
            return ('def', name[1], parameters, body, self.pipe())
        node = self.comma()
        if self.peek('as'):
            self.take('as')
            pattern = self.pattern()
            self.take('|')
            return ('bind', node, pattern, self.pipe())
        if self.peek('|'):
            self.take('|')
            node = ('pipe', node, self.pipe())
        return node

    def pattern(self):
        if self.peek() and self.peek()[0] == 'variable':
            return ('var', self.take()[1][1:])
        if self.peek('['):
            self.take('[')
            items = []
            while not self.peek(']'):
                items.append(self.pattern())
                if not self.peek(','):
                    break
                self.take(',')
            self.take(']')
            return ('array', items)
        if self.peek('{'):
            self.take('{')
            fields = []
            while not self.peek('}'):
                token = self.take()
                if token[0] != 'variable':
                    raise CompileError('unsupported object binding pattern')
                fields.append((token[1][1:], ('var', token[1][1:])))
                if not self.peek(','):
                    break
                self.take(',')
            self.take('}')
            return ('object', fields)
        raise CompileError('expected binding pattern')

    def comma(self):
        node = self.assignment()
        while self.peek(','):
            self.take(',')
            node = ('comma', node, self.assignment())
        return node

    def assignment(self):
        node = self.alternative()
        if self.peek('=') or self.peek('|='):
            operator = self.take()[1]
            node = ('assignment', operator, node, self.assignment())
        return node

    def alternative(self):
        node = self.logical_or()
        while self.peek('//'):
            self.take('//')
            node = ('binary', '//', node, self.logical_or())
        return node

    def logical_or(self):
        node = self.logical_and()
        while self.peek('or'):
            self.take('or')
            node = ('binary', 'or', node, self.logical_and())
        return node

    def logical_and(self):
        node = self.compare()
        while self.peek('and'):
            self.take('and')
            node = ('binary', 'and', node, self.compare())
        return node

    def compare(self):
        node = self.addition()
        while self.peek() and self.peek()[1] in ('==', '!=', '>', '<', '>=', '<='):
            operator = self.take()[1]
            node = ('binary', operator, node, self.addition())
        return node

    def addition(self):
        node = self.multiplication()
        while self.peek('+') or self.peek('-'):
            operator = self.take()[1]
            node = ('binary', operator, node, self.multiplication())
        return node

    def multiplication(self):
        node = self.atom()
        while self.peek('*'):
            self.take('*')
            node = ('binary', '*', node, self.atom())
        return node

    def atom(self):
        token = self.take()
        kind, value = token
        if value == '-':
            node = ('negate', self.atom())
        elif value == '.':
            node = ('identity',)
            if (self.peek() and self.peek()[0] == 'word' and
                    self.positions[self.pos][0] == self.positions[self.pos - 1][1]):
                node = ('field', node, self.take()[1])
        elif value == '(':
            node = self.pipe()
            self.take(')')
        elif value == '[':
            if self.peek(']'):
                self.take(']')
                return ('literal', [])
            node = ('array', self.pipe())
            self.take(']')
        elif value == '{':
            fields = []
            while not self.peek('}'):
                key = self.take()
                if key[0] not in ('word', 'string'):
                    raise CompileError('expected object key')
                name = json.loads(key[1]) if key[0] == 'string' else key[1]
                self.take(':')
                fields.append((name, self.assignment()))
                if not self.peek(','):
                    break
                self.take(',')
            self.take('}')
            node = ('object', fields)
        elif kind == 'string':
            try:
                node = ('literal', json.loads(value))
            except ValueError as exc:
                raise CompileError(str(exc)) from exc
        elif kind == 'number':
            node = ('literal', JqNumber(value))
        elif kind == 'variable':
            node = ('variable', value[1:])
        elif kind == 'word':
            if value in ('true', 'false', 'null'):
                node = ('literal', {'true': True, 'false': False, 'null': None}[value])
            elif value == 'if':
                node = self.conditional()
                self.take('end')
            elif value in ('reduce', 'foreach'):
                generator = self.comma()
                self.take('as')
                pattern = self.pattern()
                self.take('(')
                initial = self.pipe()
                self.take(';')
                update = self.pipe()
                extract = None
                if self.peek(';'):
                    self.take(';')
                    extract = self.pipe()
                self.take(')')
                if value == 'reduce' and extract is not None:
                    raise CompileError('reduce does not accept an extract expression')
                node = (value, generator, pattern, initial, update, extract)
            elif value == 'try':
                body = self.assignment()
                if self.peek('catch'):
                    self.take('catch')
                    node = ('try', body, self.assignment())
                else:
                    node = ('try', body, ('call', 'empty', None))
            elif self.peek('('):
                self.take('(')
                arguments = [self.pipe()]
                while self.peek(';'):
                    self.take(';')
                    arguments.append(self.pipe())
                self.take(')')
                node = (('call', value, arguments[0]) if len(arguments) == 1
                        else ('call_multi', value, arguments))
            else:
                node = ('call', value, None)
        else:
            raise CompileError('unexpected token ' + value)
        while self.peek('.') or self.peek('['):
            if self.peek('.'):
                self.take('.')
                word = self.take()
                if word[0] != 'word':
                    raise CompileError('expected field name')
                node = ('field', node, word[1])
            else:
                self.take('[')
                if self.peek(']'):
                    node = ('iterate', node)
                else:
                    index = self.pipe()
                    node = ('index', node, index)
                self.take(']')
        while self.peek('?'):
            self.take('?')
            node = ('try', node, ('call', 'empty', None))
        return node

    def conditional(self):
        condition = self.pipe()
        self.take('then')
        yes = self.pipe()
        if self.peek('elif'):
            self.take('elif')
            no = self.conditional()
        elif self.peek('else'):
            self.take('else')
            no = self.pipe()
        else:
            no = ('identity',)
        return ('if', condition, yes, no)


def truth(value):
    return value is not None and value is not False


def value_order(value):
    if value is None:
        return 0
    if value is False:
        return 1
    if value is True:
        return 2
    if is_number(value):
        return 3
    if isinstance(value, str):
        return 4
    if isinstance(value, list):
        return 5
    if isinstance(value, dict):
        return 6
    raise RuntimeErrorJq('unsupported JSON value')


def compare_values(left, right):
    left_type, right_type = value_order(left), value_order(right)
    if left_type != right_type:
        return (left_type > right_type) - (left_type < right_type)
    if left_type in (0, 1, 2):
        return 0
    if left_type == 3:
        if isinstance(left, JqNumber) and isinstance(right, JqNumber):
            left, right = left.decimal, right.decimal
        else:
            left, right = as_float(left), as_float(right)
        return (left > right) - (left < right)
    if left_type == 4:
        return (left > right) - (left < right)
    if left_type == 6:
        left_keys, right_keys = sorted(left), sorted(right)
        key_comparison = compare_values(left_keys, right_keys)
        if key_comparison:
            return key_comparison
        left, right = [left[key] for key in left_keys], [right[key] for key in right_keys]
    for a, b in zip(left, right):
        result = compare_values(a, b)
        if result:
            return result
    return (len(left) > len(right)) - (len(left) < len(right))


def jq_type_name(value):
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'boolean'
    if is_number(value):
        return 'number'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, list):
        return 'array'
    if isinstance(value, dict):
        return 'object'
    raise RuntimeErrorJq('unsupported value type')


def contains_value(container, needle, strict_types=False):
    container_type, needle_type = jq_type_name(container), jq_type_name(needle)
    if container_type != needle_type:
        if strict_types:
            raise RuntimeErrorJq('incompatible types for containment')
        return False
    if container_type == 'string':
        return needle in container
    if container_type == 'array':
        return all(any(contains_value(item, child) for item in container)
                   for child in needle)
    if container_type == 'object':
        return all(key in container and contains_value(container[key], child)
                   for key, child in needle.items())
    if container_type == 'boolean' and container != needle:
        if strict_types:
            raise RuntimeErrorJq('incompatible boolean values for containment')
        return False
    return compare_values(container, needle) == 0


def find_indices(value, needle):
    if value is None:
        if isinstance(needle, list):
            raise RuntimeErrorJq('cannot search null with an array')
        return None
    if isinstance(value, dict):
        if isinstance(needle, str):
            return None
        raise RuntimeErrorJq('cannot search an object with this pattern')
    if isinstance(value, str):
        if not isinstance(needle, str):
            raise RuntimeErrorJq('string search requires a string pattern')
        if not needle:
            return []
        result = []
        offset = 0
        while True:
            index = value.find(needle, offset)
            if index < 0:
                return result
            result.append(index)
            offset = index + 1
    if isinstance(value, list):
        if isinstance(needle, list):
            if not needle:
                return []
            return [start for start in range(len(value) - len(needle) + 1)
                    if all(compare_values(value[start + offset], item) == 0
                           for offset, item in enumerate(needle))]
        return [index for index, item in enumerate(value)
                if compare_values(item, needle) == 0]
    raise RuntimeErrorJq('index filters require a string or array')


def flatten_value(value, depth=None):
    if isinstance(value, list):
        source = value
    elif isinstance(value, dict):
        source = list(value.values())
    else:
        raise RuntimeErrorJq('flatten requires an array or object')

    result = []
    stack = [(iter(source), depth)]
    while stack:
        iterator, remaining = stack[-1]
        try:
            item = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        if isinstance(item, list) and (remaining is None or remaining > 0):
            stack.append((iter(item), None if remaining is None else remaining - 1))
        else:
            result.append(item)
    return result


def implode_value(value):
    if not isinstance(value, list):
        raise RuntimeErrorJq('implode requires an array')
    result = []
    for codepoint in value:
        if not is_number(codepoint):
            raise RuntimeErrorJq('implode requires numeric codepoints')
        if isinstance(codepoint, JqNumber):
            number = codepoint.decimal
            if not number.is_finite() or number <= -1 or number >= 0x110000:
                result.append('\ufffd')
                continue
            point = int(number)
        elif isinstance(codepoint, float):
            if not math.isfinite(codepoint) or codepoint <= -1 or codepoint >= 0x110000:
                result.append('\ufffd')
                continue
            point = int(codepoint)
        else:
            point = codepoint
        result.append(chr(point) if 0 <= point <= 0x10FFFF
                      and not 0xD800 <= point <= 0xDFFF else '\ufffd')
    return ''.join(result)


def paths(node, root, variables):
    kind = node[0]
    if kind == 'identity':
        yield ()
    elif kind == 'comma':
        yield from paths(node[1], root, variables)
        yield from paths(node[2], root, variables)
    elif kind in ('field', 'iterate', 'index'):
        for prefix in paths(node[1], root, variables):
            current = read_path(root, prefix)
            if kind == 'field':
                if current is not None and not isinstance(current, dict):
                    raise RuntimeErrorJq('cannot assign a field of this value')
                yield prefix + (node[2],)
            elif kind == 'iterate':
                if isinstance(current, dict):
                    yield from (prefix + (key,) for key in current)
                elif isinstance(current, list):
                    yield from (prefix + (index,) for index in range(len(current)))
                else:
                    raise RuntimeErrorJq('cannot iterate assignment path')
            else:
                for index in values(node[2], root, variables):
                    if isinstance(index, str) and (current is None or isinstance(current, dict)):
                        yield prefix + (index,)
                    elif is_number(index) and isinstance(current, list) and as_index(index) is not None:
                        yield prefix + (as_index(index),)
                    else:
                        raise RuntimeErrorJq('invalid assignment index')
    else:
        raise RuntimeErrorJq('invalid assignment path')


def read_path(root, path):
    for key in path:
        if root is None:
            return None
        if isinstance(root, dict) and isinstance(key, str):
            root = root.get(key)
        elif isinstance(root, list) and type(key) is int and -len(root) <= key < len(root):
            root = root[key]
        else:
            raise RuntimeErrorJq('invalid assignment path')
    return root


def write_path(root, path, value, delete=False):
    if not path:
        return None if delete else value
    if root is None and isinstance(path[0], str):
        root = {}
    if not isinstance(root, (dict, list)):
        raise RuntimeErrorJq('invalid assignment container')
    key = path[0]
    if len(path) == 1:
        if isinstance(root, dict) and isinstance(key, str):
            if delete:
                root.pop(key, None)
            else:
                root[key] = value
        elif isinstance(root, list) and type(key) is int and -len(root) <= key < len(root):
            if delete:
                del root[key]
            else:
                root[key] = value
        else:
            raise RuntimeErrorJq('invalid assignment target')
    else:
        if isinstance(root, dict) and isinstance(key, str):
            root[key] = write_path(root.get(key), path[1:], value, delete)
        elif isinstance(root, list) and type(key) is int and -len(root) <= key < len(root):
            root[key] = write_path(root[key], path[1:], value, delete)
        else:
            raise RuntimeErrorJq('invalid assignment target')
    return root


def bind_pattern(pattern, value):
    kind, content = pattern
    if kind == 'var':
        return {content: value}
    result = {}
    if kind == 'array':
        if value is not None and not isinstance(value, list):
            raise RuntimeErrorJq('cannot destructure this value as an array')
        for index, child in enumerate(content):
            item = value[index] if value is not None and index < len(value) else None
            result.update(bind_pattern(child, item))
    else:
        if value is not None and not isinstance(value, dict):
            raise RuntimeErrorJq('cannot destructure this value as an object')
        for key, child in content:
            result.update(bind_pattern(child, value.get(key) if value is not None else None))
    return result


def pattern_names(pattern):
    kind, content = pattern
    if kind == 'var':
        return {content}
    children = content if kind == 'array' else [child for _, child in content]
    return set().union(*(pattern_names(child) for child in children))


_BUILTIN_ARITIES = {('empty', 0), ('length', 0), ('not', 0), ('select', 1),
                    ('tonumber', 0), ('inputs', 0), ('input', 0), ('error', 1),
                    ('sort', 0), ('have_decnum', 0), ('map', 1), ('map_values', 1),
                    ('keys', 0), ('keys_unsorted', 0), ('has', 1), ('in', 1),
                    ('sort_by', 1), ('group_by', 1), ('unique', 0), ('unique_by', 1),
                    ('min', 0), ('max', 0), ('min_by', 1), ('max_by', 1),
                    ('add', 0), ('add', 1), ('ascii_downcase', 0), ('ascii_upcase', 0),
                    ('startswith', 1), ('endswith', 1), ('ltrimstr', 1), ('rtrimstr', 1),
                    ('trimstr', 1), ('split', 1), ('join', 1), ('type', 0),
                    ('tostring', 0), ('tojson', 0), ('fromjson', 0),
                    ('reverse', 0), ('contains', 1), ('inside', 1),
                    ('indices', 1), ('index', 1), ('rindex', 1),
                    ('flatten', 0), ('flatten', 1), ('utf8bytelength', 0),
                    ('explode', 0), ('implode', 0)}


def validate_variables(node, names, functions=None, visiting=None):
    if functions is None:
        functions = {}
    if visiting is None:
        visiting = set()
    def check(child, scope=names, definitions=functions):
        validate_variables(child, scope, definitions, visiting)

    kind = node[0]
    if kind == 'variable':
        if node[1] not in names:
            raise CompileError('$' + node[1] + ' is not defined')
    elif kind == 'def':
        _, name, parameters, body, rest = node
        definitions = dict(functions)
        definition = (parameters, body, names.copy(), definitions)
        definitions[(name, len(parameters))] = definition
        check(rest, names, definitions)
    elif kind == 'bind':
        check(node[1])
        check(node[3], names | pattern_names(node[2]))
    elif kind in ('reduce', 'foreach'):
        check(node[1])
        check(node[3])
        scope = names | pattern_names(node[2])
        check(node[4], scope)
        if node[5] is not None:
            check(node[5], scope)
    elif kind in ('array', 'negate', 'field', 'iterate'):
        check(node[1])
    elif kind in ('pipe', 'comma', 'index', 'try'):
        check(node[1])
        check(node[2])
    elif kind in ('binary', 'assignment'):
        check(node[2])
        check(node[3])
    elif kind == 'if':
        for child in node[1:]:
            check(child)
    elif kind == 'object':
        for _, child in node[1]:
            check(child)
    elif kind in ('call', 'call_multi'):
        arguments = (node[2] if kind == 'call_multi' else
                     [] if node[2] is None else [node[2]])
        for argument in arguments:
            check(argument)
        key = (node[1], len(arguments))
        if key in functions:
            definition = functions[key]
            if definition is not None and id(definition) not in visiting:
                parameters, body, captured_names, captured_functions = definition
                local_names = captured_names | {name for mode, name in parameters if mode == 'variable'}
                local_functions = dict(captured_functions)
                for mode, name in parameters:
                    if mode == 'word':
                        local_functions[(name, 0)] = None
                visiting.add(id(definition))
                try:
                    check(body, local_names, local_functions)
                finally:
                    visiting.remove(id(definition))
        elif key not in _BUILTIN_ARITIES:
            raise CompileError(f'{key[0]}/{key[1]} is not defined or supported')


def add_values(left, right):
    if left is None:
        return right
    if right is None:
        return left
    if isinstance(left, dict) and isinstance(right, dict):
        return {**left, **right}
    if is_number(left) and is_number(right):
        return as_float(left) + as_float(right)
    if type(left) is type(right) and isinstance(left, (str, list)):
        return left + right
    raise RuntimeErrorJq('incompatible operands for addition')


def join_string(value):
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if is_number(value):
        return dump_json(value, compact=True)
    raise RuntimeErrorJq('join does not support array or object elements')


def has_key(container, key):
    if container is None:
        return False
    if isinstance(container, dict) and isinstance(key, str):
        return key in container
    if isinstance(container, list) and is_number(key):
        index = as_index(key)
        return index is not None and 0 <= index < len(container)
    raise RuntimeErrorJq('cannot check membership for these values')


def values(node, value, variables):
    kind = node[0]
    if kind == 'identity':
        yield value
    elif kind == 'literal':
        yield node[1]
    elif kind == 'def':
        _, name, parameters, body, rest = node
        captured = dict(variables)
        definitions = dict(variables.get('@functions', {}))
        captured['@functions'] = definitions
        definitions[(name, len(parameters))] = ('definition', parameters, body, captured)
        yield from values(rest, value, {**variables, '@functions': definitions})
    elif kind == 'negate':
        for item in values(node[1], value, variables):
            if not is_number(item):
                raise RuntimeErrorJq('cannot negate this value')
            yield item.negate() if isinstance(item, JqNumber) else -item
    elif kind == 'variable':
        if node[1] not in variables:
            raise CompileError('$' + node[1] + ' is not defined')
        yield variables[node[1]]
    elif kind == 'field':
        for target in values(node[1], value, variables):
            if target is None:
                yield None
            elif isinstance(target, dict):
                yield target.get(node[2])
            else:
                raise RuntimeErrorJq('cannot index this value with a string')
    elif kind == 'iterate':
        for target in values(node[1], value, variables):
            if isinstance(target, dict):
                yield from target.values()
            elif isinstance(target, list):
                yield from target
            else:
                raise RuntimeErrorJq('cannot iterate over this value')
    elif kind == 'index':
        for target in values(node[1], value, variables):
            for index in values(node[2], value, variables):
                if isinstance(target, dict) and isinstance(index, str):
                    yield target.get(index)
                elif isinstance(target, list) and is_number(index):
                    position = as_index(index)
                    yield target[position] if position is not None and -len(target) <= position < len(target) else None
                elif target is None:
                    yield None
                else:
                    raise RuntimeErrorJq('invalid index')
    elif kind == 'pipe':
        for item in values(node[1], value, variables):
            yield from values(node[2], item, variables)
    elif kind == 'bind':
        for item in values(node[1], value, variables):
            scope = {**variables, **bind_pattern(node[2], item)}
            yield from values(node[3], value, scope)
    elif kind in ('reduce', 'foreach'):
        generator, pattern, initial, update, extract = node[1:]
        for index, state in enumerate(values(initial, value, variables)):
            source = value if kind == 'foreach' or index == 0 else None
            for item in values(generator, source, variables):
                scope = {**variables, **bind_pattern(pattern, item)}
                state_before = state
                state = None
                for result in values(update, state_before, scope):
                    state = result
                    if kind == 'foreach':
                        yield from values(extract or ('identity',), state, scope)
            if kind == 'reduce':
                yield state
    elif kind == 'comma':
        yield from values(node[1], value, variables)
        yield from values(node[2], value, variables)
    elif kind == 'array':
        yield list(values(node[1], value, variables))
    elif kind == 'object':
        def build(fields, index, result):
            if index == len(fields):
                yield result
                return
            name, expression = fields[index]
            for field_value in values(expression, value, variables):
                yield from build(fields, index + 1, {**result, name: field_value})
        yield from build(node[1], 0, {})
    elif kind == 'if':
        for condition in values(node[1], value, variables):
            yield from values(node[2] if truth(condition) else node[3], value, variables)
    elif kind == 'try':
        try:
            yield from values(node[1], value, variables)
        except RuntimeErrorJq as exc:
            yield from values(node[2], str(exc), variables)
    elif kind == 'assignment':
        operator, target, update = node[1:]
        selected_paths = list(paths(target, value, variables))
        if operator == '=':
            for result in values(update, value, variables):
                changed = copy.deepcopy(value)
                for path in selected_paths:
                    changed = write_path(changed, path, copy.deepcopy(result))
                yield changed
        else:
            changed = copy.deepcopy(value)
            for path in selected_paths:
                result = next(values(update, read_path(changed, path), variables), _MISSING)
                changed = write_path(changed, path, result, delete=result is _MISSING)
            yield changed
    elif kind == 'binary':
        op, left, right = node[1:]
        if op == '//':
            found = False
            for item in values(left, value, variables):
                if truth(item):
                    found = True
                    yield item
            if not found:
                yield from values(right, value, variables)
            return
        if op in ('and', 'or'):
            for item in values(left, value, variables):
                if op == 'and' and not truth(item):
                    yield False
                elif op == 'or' and truth(item):
                    yield True
                else:
                    for other in values(right, value, variables):
                        yield truth(other)
            return
        for right_value in values(right, value, variables):
            for left_value in values(left, value, variables):
                if op == '+':
                    yield add_values(left_value, right_value)
                elif op in ('-', '*'):
                    if not is_number(left_value) or not is_number(right_value):
                        raise RuntimeErrorJq('incompatible numeric operands')
                    left_number, right_number = as_float(left_value), as_float(right_value)
                    yield left_number - right_number if op == '-' else left_number * right_number
                elif op in ('==', '!='):
                    equal = compare_values(left_value, right_value) == 0
                    yield equal if op == '==' else not equal
                else:
                    comparison = compare_values(left_value, right_value)
                    yield {'>': comparison > 0, '<': comparison < 0,
                           '>=': comparison >= 0, '<=': comparison <= 0}[op]
    elif kind in ('call', 'call_multi'):
        name = node[1]
        arguments = (node[2] if kind == 'call_multi' else
                     [] if node[2] is None else [node[2]])
        definition = variables.get('@functions', {}).get((name, len(arguments)))
        if definition is not None:
            if definition[0] == 'filter':
                yield from values(definition[1], value, definition[2])
                return
            _, parameters, body, captured = definition

            def apply_parameters(index, scope):
                if index == len(parameters):
                    yield from values(body, value, scope)
                    return
                mode, parameter = parameters[index]
                argument = arguments[index]
                if mode == 'word':
                    definitions = dict(scope.get('@functions', {}))
                    definitions[(parameter, 0)] = ('filter', argument, variables)
                    yield from apply_parameters(index + 1, {**scope, '@functions': definitions})
                else:
                    for item in values(argument, value, variables):
                        yield from apply_parameters(index + 1, {**scope, parameter: item})

            yield from apply_parameters(0, captured)
            return
        argument = arguments[0] if len(arguments) == 1 else None
        if name == 'empty' and argument is None:
            return
        if name == 'modulemeta':
            raise RuntimeErrorJq('modulemeta is not supported yet')
        if name == 'type' and argument is None:
            yield jq_type_name(value)
        elif name == 'tostring' and argument is None:
            yield value if isinstance(value, str) else dump_json(value, compact=True)
        elif name == 'tojson' and argument is None:
            yield dump_json(value, compact=True)
        elif name == 'fromjson' and argument is None:
            if not isinstance(value, str):
                raise RuntimeErrorJq('fromjson requires a string')
            parsed = list(parse_json_values([value]))
            if len(parsed) != 1:
                raise RuntimeErrorJq('fromjson requires exactly one JSON value')
            yield parsed[0]
        elif name == 'reverse' and argument is None:
            if not isinstance(value, list):
                raise RuntimeErrorJq('reverse requires an array')
            yield list(reversed(value))
        elif name == 'flatten' and len(arguments) == 0:
            yield flatten_value(value)
        elif name == 'flatten' and len(arguments) == 1:
            for depth in values(arguments[0], value, variables):
                if not is_number(depth):
                    raise RuntimeErrorJq('flatten depth must be a number')
                if isinstance(depth, JqNumber):
                    decimal_depth = depth.decimal
                    if decimal_depth != decimal_depth.to_integral_value():
                        raise RuntimeErrorJq('fractional flatten depth is not supported')
                    depth = int(decimal_depth)
                elif isinstance(depth, float):
                    if not depth.is_integer():
                        raise RuntimeErrorJq('fractional flatten depth is not supported')
                    depth = int(depth)
                if depth < 0:
                    raise RuntimeErrorJq('flatten depth must not be negative')
                yield flatten_value(value, depth)
        elif name in ('contains', 'inside') and argument is not None:
            for other in values(argument, value, variables):
                yield (contains_value(value, other, strict_types=True) if name == 'contains'
                       else contains_value(other, value, strict_types=True))
        elif name in ('indices', 'index', 'rindex') and argument is not None:
            for needle in values(argument, value, variables):
                matches = find_indices(value, needle)
                if name == 'indices':
                    yield matches
                elif not matches:
                    yield None
                else:
                    yield matches[0] if name == 'index' else matches[-1]
        elif name == 'have_decnum' and argument is None:
            yield True
        elif name == 'length' and argument is None:
            if value is None:
                yield 0
            elif isinstance(value, (str, list, dict)):
                yield len(value)
            elif isinstance(value, JqNumber):
                yield JqNumber.from_decimal(value.decimal.copy_abs())
            elif type(value) in (int, float):
                yield abs(value)
            else:
                raise RuntimeErrorJq('length not defined for this value')
        elif name == 'utf8bytelength' and argument is None:
            if not isinstance(value, str):
                raise RuntimeErrorJq('utf8bytelength requires a string')
            try:
                yield len(value.encode('utf-8'))
            except UnicodeEncodeError as exc:
                raise RuntimeErrorJq('utf8bytelength requires valid Unicode') from exc
        elif name == 'explode' and argument is None:
            if not isinstance(value, str):
                raise RuntimeErrorJq('explode requires a string')
            try:
                value.encode('utf-8')
            except UnicodeEncodeError as exc:
                raise RuntimeErrorJq('explode requires valid Unicode') from exc
            yield [ord(character) for character in value]
        elif name == 'implode' and argument is None:
            yield implode_value(value)
        elif name in ('ascii_downcase', 'ascii_upcase') and argument is None:
            if not isinstance(value, str):
                raise RuntimeErrorJq(name + ' requires a string')
            if name == 'ascii_downcase':
                yield value.translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ',
                                                    'abcdefghijklmnopqrstuvwxyz'))
            else:
                yield value.translate(str.maketrans('abcdefghijklmnopqrstuvwxyz',
                                                    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
        elif name in ('startswith', 'endswith', 'ltrimstr', 'rtrimstr', 'trimstr') and argument is not None:
            for text in values(argument, value, variables):
                if not isinstance(value, str) or not isinstance(text, str):
                    raise RuntimeErrorJq(name + ' requires string inputs')
                if name == 'startswith':
                    yield value.startswith(text)
                elif name == 'endswith':
                    yield value.endswith(text)
                elif name == 'ltrimstr':
                    yield value[len(text):] if text and value.startswith(text) else value
                elif name == 'rtrimstr':
                    yield value[:-len(text)] if text and value.endswith(text) else value
                else:
                    result = value[len(text):] if text and value.startswith(text) else value
                    yield result[:-len(text)] if text and result.endswith(text) else result
        elif name == 'split' and argument is not None:
            for separator in values(argument, value, variables):
                if not isinstance(value, str) or not isinstance(separator, str):
                    raise RuntimeErrorJq('split requires string inputs')
                yield [] if not value else (
                    list(value) if separator == '' else value.split(separator))
        elif name == 'join' and argument is not None:
            for separator in values(argument, value, variables):
                if not isinstance(separator, str):
                    raise RuntimeErrorJq('join separator must be a string')
                if isinstance(value, dict):
                    items = list(value.values())
                elif isinstance(value, list):
                    items = value
                else:
                    raise RuntimeErrorJq('join requires an array or object')
                yield separator.join(join_string(item) for item in items)
        elif name in ('keys', 'keys_unsorted') and argument is None:
            if isinstance(value, dict):
                yield sorted(value) if name == 'keys' else list(value)
            elif isinstance(value, list):
                yield list(range(len(value)))
            else:
                raise RuntimeErrorJq('keys requires an array or object')
        elif name in ('has', 'in') and argument is not None:
            for item in values(argument, value, variables):
                yield has_key(value, item) if name == 'has' else has_key(item, value)
        elif name in ('map', 'map_values') and argument is not None:
            if not isinstance(value, (list, dict)):
                raise RuntimeErrorJq('cannot iterate over this value')
            items = value.items() if isinstance(value, dict) else enumerate(value)
            if name == 'map':
                yield [result for _, item in items for result in values(argument, item, variables)]
            elif isinstance(value, dict):
                result = {}
                for key, item in items:
                    first = next(values(argument, item, variables), _MISSING)
                    if first is not _MISSING:
                        result[key] = first
                yield result
            else:
                result = []
                for _, item in items:
                    first = next(values(argument, item, variables), _MISSING)
                    if first is not _MISSING:
                        result.append(first)
                yield result
        elif name == 'not' and argument is None:
            yield not truth(value)
        elif name == 'select' and argument is not None:
            for condition in values(argument, value, variables):
                if truth(condition):
                    yield value
        elif name == 'tonumber' and argument is None:
            if is_number(value):
                yield value
            elif isinstance(value, str):
                try:
                    parsed = decode_atom(value)
                except RuntimeErrorJq as exc:
                    raise RuntimeErrorJq('cannot parse number') from exc
                if not is_number(parsed) and not (parsed is None and value.lower() in ('nan', '+nan', '-nan')):
                    raise RuntimeErrorJq('cannot parse number')
                yield parsed
            else:
                raise RuntimeErrorJq('cannot convert value to number')
        elif name == 'inputs' and argument is None:
            yield from variables['@inputs']
        elif name == 'input' and argument is None:
            item = next(variables['@inputs'], _MISSING)
            if item is _MISSING:
                raise RuntimeErrorJq('input exhausted')
            yield item
        elif name == 'error' and argument is not None:
            for message in values(argument, value, variables):
                raise RuntimeErrorJq(str(message))
        elif name == 'add':
            source = values(argument, value, variables) if argument is not None else values(('iterate', ('identity',)), value, variables)
            total = None
            for item in source:
                total = add_values(total, item)
            yield total
        elif name in ('sort', 'sort_by', 'group_by', 'unique', 'unique_by',
                      'min', 'max', 'min_by', 'max_by'):
            if not isinstance(value, list):
                raise RuntimeErrorJq('ordering requires an array')
            if name in ('min', 'min_by', 'max', 'max_by'):
                best_key, best_value = _MISSING, None
                for item in value:
                    key = [item] if argument is None else list(values(argument, item, variables))
                    comparison = 0 if best_key is _MISSING else compare_values(key, best_key)
                    if best_key is _MISSING or (comparison >= 0 if name.startswith('max') else comparison < 0):
                        best_key, best_value = key, item
                yield best_value
                return
            pairs = [([item] if argument is None else list(values(argument, item, variables)), item)
                     for item in value]
            pairs.sort(key=functools.cmp_to_key(lambda a, b: compare_values(a[0], b[0])))
            if name in ('sort', 'sort_by'):
                yield [item for _, item in pairs]
            else:
                groups = []
                previous = _MISSING
                for key, item in pairs:
                    if previous is _MISSING or compare_values(previous, key) != 0:
                        groups.append([])
                        previous = key
                    groups[-1].append(item)
                yield groups if name == 'group_by' else [group[0] for group in groups]
        elif name != 'empty':
            raise CompileError('unknown or unsupported filter ' + name)
    else:
        raise CompileError('unsupported expression')


_MISSING = object()


def parse_json_values(chunks, sequence=False):
    reader = StreamReader(chunks)
    parser = ValueParser(reader)
    while True:
        reader.whitespace()
        if not reader.peek():
            return
        item = parser.value()
        if sequence and is_number(item) and not reader.peek():
            raise RuntimeErrorJq('potentially truncated top-level numeric value')
        yield item


class StreamParseError(RuntimeErrorJq):
    def __init__(self, message, path):
        super().__init__(message)
        self.path = path


class StreamReader:
    """Read characters across input chunks without materializing the JSON tree."""

    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.buffer = ''
        self.offset = 0

    def peek(self):
        while self.offset == len(self.buffer):
            try:
                self.buffer = next(self.chunks)
            except StopIteration:
                return ''
            self.offset = 0
        return self.buffer[self.offset]

    def take(self):
        char = self.peek()
        if char:
            self.offset += 1
        return char

    def whitespace(self):
        while self.peek() and self.peek() in ' \t\r\n':
            self.take()


NUMBER_LITERAL = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')


def decode_atom(token):
    constants = {'null': None, 'true': True, 'false': False}
    if token in constants:
        return constants[token]
    if token.lower() in ('nan', '+nan', '-nan'):
        return None
    if token.lower() in ('inf', '+inf', 'infinity', '+infinity'):
        return sys.float_info.max
    if token.lower() in ('-inf', '-infinity'):
        return -sys.float_info.max
    if not NUMBER_LITERAL.fullmatch(token):
        raise RuntimeErrorJq('invalid JSON literal')
    return JqNumber(token)


def decode_string(text):
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise RuntimeErrorJq('invalid JSON string: ' + str(exc)) from exc
    result = []
    for char in value:
        code = ord(char)
        if 0xD800 <= code <= 0xDBFF:
            raise RuntimeErrorJq('invalid high surrogate')
        result.append('\ufffd' if 0xDC00 <= code <= 0xDFFF else char)
    return ''.join(result)


class ValueParser:
    """Parse consecutive JSON values without requiring the standard JSON grammar."""

    def __init__(self, reader):
        self.reader = reader

    def string(self):
        text = self.reader.take()
        escaped = False
        while True:
            char = self.reader.take()
            if not char:
                raise RuntimeErrorJq('unfinished JSON string')
            text += char
            if not escaped and char == '"':
                break
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
        return decode_string(text)

    def value(self):
        reader = self.reader
        reader.whitespace()
        char = reader.peek()
        if not char:
            raise RuntimeErrorJq('unfinished JSON value')
        if char == '"':
            return self.string()
        if char == '[':
            reader.take()
            reader.whitespace()
            result = []
            if reader.peek() == ']':
                reader.take()
                return result
            while True:
                result.append(self.value())
                reader.whitespace()
                separator = reader.take()
                if separator == ']':
                    return result
                if separator != ',':
                    raise RuntimeErrorJq('expected array separator or end')
        if char == '{':
            reader.take()
            reader.whitespace()
            result = {}
            if reader.peek() == '}':
                reader.take()
                return result
            while True:
                reader.whitespace()
                if reader.peek() != '"':
                    raise RuntimeErrorJq('expected object key')
                key = self.string()
                reader.whitespace()
                if reader.take() != ':':
                    raise RuntimeErrorJq('expected colon after object key')
                result[key] = self.value()
                reader.whitespace()
                separator = reader.take()
                if separator == '}':
                    return result
                if separator != ',':
                    raise RuntimeErrorJq('expected object separator or end')
        token = ''
        while reader.peek() and reader.peek() not in ' \t\r\n,]}:{["':
            token += reader.take()
        return decode_atom(token)


class StreamParser:
    def __init__(self, chunks):
        self.reader = StreamReader(chunks)

    def fail(self, message, path):
        raise StreamParseError(message, path)

    def string(self, path):
        text = self.reader.take()
        escaped = False
        while True:
            char = self.reader.take()
            if not char:
                self.fail('unfinished JSON string', path)
            text += char
            if not escaped and char == '"':
                break
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
        try:
            return decode_string(text)
        except RuntimeErrorJq as exc:
            self.fail(str(exc), path)

    def value(self, path):
        reader = self.reader
        reader.whitespace()
        char = reader.peek()
        if not char:
            self.fail('unfinished JSON term at EOF', path)
        if char == '[':
            reader.take()
            reader.whitespace()
            if reader.peek() == ']':
                reader.take()
                yield [path, []]
                return None
            index = 0
            while True:
                child_path = path + [index]
                if reader.peek() == ']':
                    self.fail('expected another array element', child_path)
                leaf = yield from self.value(child_path)
                reader.whitespace()
                separator = reader.take()
                if separator not in (',', ']'):
                    self.fail('expected array separator or end', child_path)
                if leaf is not None:
                    yield leaf
                if separator == ']':
                    yield [child_path]
                    return None
                index += 1
                reader.whitespace()
        if char == '{':
            reader.take()
            reader.whitespace()
            if reader.peek() == '}':
                reader.take()
                yield [path, {}]
                return None
            while True:
                if reader.peek() != '"':
                    self.fail('expected object key', path + [None])
                key = self.string(path + [None])
                reader.whitespace()
                if reader.take() != ':':
                    self.fail('expected colon after object key', path + [None])
                child_path = path + [key]
                leaf = yield from self.value(child_path)
                reader.whitespace()
                separator = reader.take()
                if separator not in (',', '}'):
                    self.fail('expected object separator or end', child_path)
                if leaf is not None:
                    yield leaf
                if separator == '}':
                    yield [child_path]
                    return None
                reader.whitespace()
        if char == '"':
            return [path, self.string(path)]
        token = ''
        while reader.peek() and reader.peek() not in ' \t\r\n,]}:{["':
            token += reader.take()
        try:
            item = decode_atom(token)
        except RuntimeErrorJq as exc:
            self.fail(str(exc), path)
        return [path, item]

    def records(self):
        while True:
            self.reader.whitespace()
            if not self.reader.peek():
                return
            leaf = yield from self.value([])
            if leaf is not None:
                yield leaf


def parse_json_stream(chunks, errors):
    try:
        yield from StreamParser(chunks).records()
    except StreamParseError as exc:
        if not errors:
            raise
        yield [str(exc), exc.path]


def sequence_segments(chunks):
    """Drop text before the first record separator and split at later separators."""
    pending = ''
    seen_separator = False
    for chunk in chunks:
        parts = chunk.split('\x1e')
        if seen_separator:
            pending += parts[0]
        if len(parts) > 1:
            if seen_separator:
                yield pending
            seen_separator = True
            for part in parts[1:-1]:
                yield part
            pending = parts[-1]
    yield pending if seen_separator else None


def parse_json_sequence(chunks, stream, stream_errors):
    for segment in sequence_segments(chunks):
        if segment is None:
            if stream_errors:
                yield ['unfinished abandoned text at EOF', []]
            else:
                print('jq: ignoring parse error: unfinished abandoned text at EOF', file=sys.stderr)
            return
        try:
            records = (StreamParser([segment]).records() if stream
                       else parse_json_values([segment], sequence=True))
            yield from records
        except RuntimeErrorJq as exc:
            if stream_errors:
                yield [str(exc), exc.path if isinstance(exc, StreamParseError) else []]
            else:
                print('jq: ignoring parse error: ' + str(exc), file=sys.stderr)


class InputStream:
    """One shared input cursor for automatic iteration and input/inputs."""

    def __init__(self, paths, raw_mode, slurp, stream=False, stream_errors=False, sequence=False):
        self.paths = paths or ['-']
        self.raw_mode = raw_mode
        self.slurp = slurp
        self.stream = stream
        self.stream_errors = stream_errors
        self.sequence = sequence
        self.file_error = False

    def chunks(self):
        for path in self.paths:
            if path == '-':
                decoder = codecs.getincrementaldecoder('utf-8')('replace')
                while True:
                    data = sys.stdin.buffer.read1(65536)
                    if not data:
                        break
                    yield decoder.decode(data)
                tail = decoder.decode(b'', final=True)
                if tail:
                    yield tail
            else:
                try:
                    with open(path, encoding='utf-8', errors='replace', newline='') as source:
                        while chunk := source.read(65536):
                            yield chunk
                except OSError as exc:
                    self.file_error = True
                    print(f'jq: could not open file {path}: {exc.strerror}', file=sys.stderr)

    def __iter__(self):
        if self.raw_mode and self.slurp:
            yield ''.join(self.chunks())
        elif self.raw_mode:
            pending = ''
            for chunk in self.chunks():
                pending += chunk
                lines = pending.split('\n')
                pending = lines.pop()
                yield from lines
            if pending:
                yield pending
        else:
            if self.sequence:
                records = parse_json_sequence(self.chunks(), self.stream, self.stream_errors)
            elif self.stream:
                records = parse_json_stream(self.chunks(), self.stream_errors)
            else:
                records = parse_json_values(self.chunks())
            if self.slurp:
                yield list(records)
            else:
                yield from records


def strip_jq_comments(source):
    """Remove line comments while preserving quoted strings and line breaks."""
    result = []
    index = 0
    in_string = False
    escaped = False
    while index < len(source):
        char = source[index]
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue
        if char == '#':
            index += 1
            while True:
                start = index
                while index < len(source) and source[index] != '\n':
                    index += 1
                line = source[start:index]
                continued = (len(line) - len(line.rstrip('\\'))) % 2 == 1
                if index < len(source):
                    result.append('\n')
                    index += 1
                if not continued or index >= len(source):
                    break
            continue
        result.append(char)
        index += 1
    return ''.join(result)


def find_module(module_name, library_paths):
    if not module_name:
        raise CompileError('module path must not be empty')
    if module_name.startswith('~/') or module_name.startswith('$ORIGIN/'):
        raise CompileError('module path prefix is not supported yet: ' + module_name)
    if module_name.endswith('.json'):
        raise CompileError('JSON modules are not supported yet')

    path = Path(module_name)
    if path.is_absolute():
        roots = [Path('/')]
    elif module_name in ('.', './') or module_name.startswith('./') or module_name.startswith('../'):
        roots = [Path.cwd()]
    else:
        if not library_paths:
            raise CompileError('default module search paths are not supported; pass -L directory')
        roots = [Path(directory) for directory in library_paths]

    for root in roots:
        base = path if path.is_absolute() else root / path
        if module_name.endswith('.jq'):
            candidates = (base,)
        else:
            candidates = (Path(str(base) + '.jq'), base / (base.name + '.jq'))
        for candidate in candidates:
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                continue
    return None


def expand_module_includes(source, library_paths, stack=()):
    """Expand the supported include subset before compiling the filter."""
    source = strip_jq_comments(source)
    result = []
    index = 0
    in_string = False
    escaped = False
    while index < len(source):
        char = source[index]
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            result.append(char)
            in_string = True
            index += 1
            continue

        tail = source[index:]
        boundary = index == 0 or not (source[index - 1].isalnum() or source[index - 1] == '_')
        if boundary and re.match(r'import\b\s*"', tail):
            raise CompileError('import modules are not supported yet')
        if boundary and re.match(r'module\b\s+', tail):
            raise CompileError('module metadata is not supported yet')
        if boundary and re.match(r'modulemeta\b', tail):
            raise CompileError('modulemeta is not supported yet')
        directive = re.match(r'include\b\s*("(?:\\.|[^"\\])*")\s*;', tail) if boundary else None
        if directive:
            try:
                module_name = json.loads(directive.group(1))
            except ValueError as exc:
                raise CompileError('invalid module path string') from exc
            module_path = find_module(module_name, library_paths)
            if module_path is None:
                raise CompileError('module not found: ' + module_name)
            try:
                resolved = module_path.resolve()
                module_source = module_path.read_text(encoding='utf-8')
            except (OSError, UnicodeError, RuntimeError) as exc:
                raise CompileError('cannot read module ' + module_name + ': ' + str(exc)) from exc
            if resolved in stack:
                raise CompileError('recursive module include: ' + module_name)
            result.append(expand_module_includes(module_source, library_paths, stack + (resolved,)))
            result.append('\n')
            index += directive.end()
            continue

        result.append(char)
        index += 1
    return ''.join(result)


def main():
    flags = set()
    variables = {}
    library_paths = []
    argv = sys.argv[1:]
    if argv == ['--version']:
        print('jq-reconstruction-wip')
        return 0
    try:
        while argv and argv[0].startswith('-'):
            option = argv.pop(0)
            if option == '-L':
                if not argv:
                    raise CompileError(option + ' requires a directory')
                library_paths.append(argv.pop(0))
            elif option in ('--arg', '--argjson'):
                if len(argv) < 2:
                    raise CompileError(option + ' requires name and value')
                name, raw = argv.pop(0), argv.pop(0)
                if option == '--argjson':
                    parsed = list(parse_json_values([raw]))
                    if len(parsed) != 1:
                        raise CompileError('--argjson requires one JSON value')
                    variables[name] = parsed[0]
                else:
                    variables[name] = raw
            elif option == '--raw-output0':
                flags.add('raw-output0')
            elif option in ('--stream', '--stream-errors'):
                flags.add('stream')
                if option == '--stream-errors':
                    flags.add('stream-errors')
            elif option == '--seq':
                flags.add('seq')
            elif option.startswith('--') or any(c not in 'nscerR' for c in option[1:]):
                raise CompileError('unsupported option ' + option)
            else:
                flags.update(option[1:])
        if not argv:
            raise CompileError('expected one filter')
        program_text = expand_module_includes(argv.pop(0), library_paths)
        program = Parser(program_text).parse()
        validate_variables(program, set(variables))
        input_stream = InputStream(argv, 'R' in flags, 's' in flags,
                                   'stream' in flags, 'stream-errors' in flags, 'seq' in flags)
        cursor = iter(input_stream)
        variables['@inputs'] = cursor
        source = [None] if 'n' in flags else cursor
        output_count = 0
        last = None
        for item in source:
            for result in values(program, item, variables):
                output_count += 1
                last = result
                raw_output = ('r' in flags or 'raw-output0' in flags) and isinstance(result, str)
                if raw_output:
                    if 'raw-output0' in flags and '\0' in result:
                        raise RuntimeErrorJq('cannot output string containing NUL with --raw-output0')
                    output = result
                else:
                    output = dump_json(result, compact='c' in flags)
                prefix = '\x1e' if 'seq' in flags and not raw_output else ''
                sys.stdout.write(prefix + output + ('\0' if 'raw-output0' in flags else '\n'))
        if input_stream.file_error:
            return 2
        if 'e' in flags:
            return 4 if output_count == 0 else 0 if truth(last) else 1
        return 0
    except CompileError as exc:
        print('jq: compile error: ' + str(exc), file=sys.stderr)
        return 3
    except (RuntimeErrorJq, UnicodeError, ValueError) as exc:
        print('jq: error: ' + str(exc), file=sys.stderr)
        return 5
