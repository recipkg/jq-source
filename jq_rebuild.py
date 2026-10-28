"""Initial jq-compatible filter interpreter, generated from the Recipkg recipe.

This is deliberately incomplete. Reject unsupported operations explicitly.
"""
import copy
import json
import re
import sys


class CompileError(Exception):
    pass


class RuntimeErrorJq(Exception):
    pass


TOKEN = re.compile(
    r'\s*(?:(?P<string>"(?:\\.|[^"\\])*")|(?P<number>-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)'
    r'|(?P<variable>\$[A-Za-z_][A-Za-z_0-9]*)|(?P<word>[A-Za-z_][A-Za-z_0-9]*)'
    r'|(?P<op>==|!=|>=|<=|//|\|=|[.\[\](),|+<>=?]))'
)


class Parser:
    def __init__(self, text):
        self.tokens = []
        while text:
            if not text.strip():
                break
            match = TOKEN.match(text)
            if not match:
                raise CompileError('unsupported or invalid syntax near ' + repr(text[:20]))
            self.tokens.append((match.lastgroup, match.group(match.lastgroup)))
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
        node = self.comma()
        while self.peek('|'):
            self.take('|')
            node = ('pipe', node, self.comma())
        return node

    def comma(self):
        node = self.assignment()
        while self.peek(','):
            self.take(',')
            node = ('comma', node, self.assignment())
        return node

    def assignment(self):
        node = self.compare()
        if self.peek('=') or self.peek('|='):
            operator = self.take()[1]
            node = ('assignment', operator, node, self.assignment())
        return node

    def compare(self):
        node = self.addition()
        while self.peek() and self.peek()[1] in ('==', '!=', '>', '<', '>=', '<=', '//'):
            operator = self.take()[1]
            node = ('binary', operator, node, self.addition())
        return node

    def addition(self):
        node = self.atom()
        while self.peek('+'):
            self.take('+')
            node = ('binary', '+', node, self.atom())
        return node

    def atom(self):
        token = self.take()
        kind, value = token
        if value == '.':
            node = ('identity',)
            if self.peek() and self.peek()[0] == 'word':
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
        elif kind == 'string':
            try:
                node = ('literal', json.loads(value))
            except ValueError as exc:
                raise CompileError(str(exc)) from exc
        elif kind == 'number':
            node = ('literal', json.loads(value))
        elif kind == 'variable':
            node = ('variable', value[1:])
        elif kind == 'word':
            if value in ('true', 'false', 'null'):
                node = ('literal', {'true': True, 'false': False, 'null': None}[value])
            elif value == 'try':
                body = self.assignment()
                if self.peek('catch'):
                    self.take('catch')
                    node = ('try', body, self.assignment())
                else:
                    node = ('try', body, ('call', 'empty', None))
            elif self.peek('('):
                self.take('(')
                argument = self.pipe()
                self.take(')')
                node = ('call', value, argument)
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


def truth(value):
    return value is not None and value is not False


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
                    elif type(index) is int and isinstance(current, list):
                        yield prefix + (index,)
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


def values(node, value, variables):
    kind = node[0]
    if kind == 'identity':
        yield value
    elif kind == 'literal':
        yield node[1]
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
                elif isinstance(target, list) and isinstance(index, int) and not isinstance(index, bool):
                    yield target[index] if -len(target) <= index < len(target) else None
                elif target is None:
                    yield None
                else:
                    raise RuntimeErrorJq('invalid index')
    elif kind == 'pipe':
        for item in values(node[1], value, variables):
            yield from values(node[2], item, variables)
    elif kind == 'comma':
        yield from values(node[1], value, variables)
        yield from values(node[2], value, variables)
    elif kind == 'array':
        yield list(values(node[1], value, variables))
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
            good = [item for item in values(left, value, variables) if truth(item)]
            yield from good if good else values(right, value, variables)
            return
        for right_value in values(right, value, variables):
            for left_value in values(left, value, variables):
                if op == '+':
                    if left_value is None:
                        yield right_value
                    elif right_value is None:
                        yield left_value
                    elif isinstance(left_value, dict) and isinstance(right_value, dict):
                        yield {**left_value, **right_value}
                    elif type(left_value) is type(right_value) and isinstance(left_value, (int, float, str, list)):
                        yield left_value + right_value
                    else:
                        raise RuntimeErrorJq('incompatible operands for addition')
                elif op in ('==', '!='):
                    equal = (type(left_value) is type(right_value) or
                             type(left_value) in (int, float) and type(right_value) in (int, float)) and left_value == right_value
                    yield equal if op == '==' else not equal
                else:
                    if type(left_value) is not type(right_value):
                        raise RuntimeErrorJq('cross-type ordering not implemented')
                    try:
                        yield {'>': lambda: left_value > right_value, '<': lambda: left_value < right_value,
                               '>=': lambda: left_value >= right_value, '<=': lambda: left_value <= right_value}[op]()
                    except TypeError as exc:
                        raise RuntimeErrorJq('ordering not implemented for this type') from exc
    elif kind == 'call':
        name, argument = node[1:]
        if name == 'empty' and argument is None:
            return
        if name == 'length' and argument is None:
            if value is None:
                yield 0
            elif isinstance(value, (str, list, dict)):
                yield len(value)
            elif type(value) in (int, float):
                yield abs(value)
            else:
                raise RuntimeErrorJq('length not defined for this value')
        elif name == 'not' and argument is None:
            yield not truth(value)
        elif name == 'select' and argument is not None:
            for condition in values(argument, value, variables):
                if truth(condition):
                    yield value
        elif name == 'tonumber' and argument is None:
            if type(value) in (int, float):
                yield value
            elif isinstance(value, str):
                try:
                    parsed = json.loads(value)
                except ValueError as exc:
                    raise RuntimeErrorJq('cannot parse number') from exc
                if type(parsed) not in (int, float):
                    raise RuntimeErrorJq('cannot parse number')
                yield parsed
            else:
                raise RuntimeErrorJq('cannot convert value to number')
        elif name != 'empty':
            raise CompileError('unknown or unsupported filter ' + name)
    else:
        raise CompileError('unsupported expression')


_MISSING = object()


def inputs(raw, raw_mode, slurp):
    if raw_mode:
        yield from [raw] if slurp else raw.splitlines()
        return
    decoder = json.JSONDecoder()
    position = 0
    found = []
    while position < len(raw):
        while position < len(raw) and raw[position].isspace():
            position += 1
        if position == len(raw):
            break
        try:
            item, position = decoder.raw_decode(raw, position)
        except ValueError as exc:
            raise RuntimeErrorJq('invalid JSON input: ' + str(exc)) from exc
        if slurp:
            found.append(item)
        else:
            yield item
    if slurp:
        yield found


def main():
    flags = set()
    variables = {}
    argv = sys.argv[1:]
    if argv == ['--version']:
        print('jq-reconstruction-wip')
        return 0
    try:
        while argv and argv[0].startswith('-'):
            option = argv.pop(0)
            if option in ('--arg', '--argjson'):
                if len(argv) < 2:
                    raise CompileError(option + ' requires name and value')
                name, raw = argv.pop(0), argv.pop(0)
                variables[name] = json.loads(raw) if option == '--argjson' else raw
            elif option.startswith('--') or any(c not in 'nscerR' for c in option[1:]):
                raise CompileError('unsupported option ' + option)
            else:
                flags.update(option[1:])
        if len(argv) != 1:
            raise CompileError('expected one filter; input files are not yet supported')
        program = Parser(argv[0]).parse()
        raw = '' if 'n' in flags else sys.stdin.read()
        source = [None] if 'n' in flags else inputs(raw, 'R' in flags, 's' in flags)
        output_count = 0
        last = None
        for item in source:
            for result in values(program, item, variables):
                output_count += 1
                last = result
                if 'r' in flags and isinstance(result, str):
                    print(result)
                else:
                    print(json.dumps(result, ensure_ascii=False, separators=(',', ':') if 'c' in flags else None,
                                     indent=None if 'c' in flags else 2))
        if 'e' in flags:
            return 4 if output_count == 0 else 0 if truth(last) else 1
        return 0
    except CompileError as exc:
        print('jq: compile error: ' + str(exc), file=sys.stderr)
        return 3
    except (RuntimeErrorJq, UnicodeError, ValueError) as exc:
        print('jq: error: ' + str(exc), file=sys.stderr)
        return 5
