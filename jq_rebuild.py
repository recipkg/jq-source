"""Initial jq-compatible filter interpreter, generated from the Recipkg recipe.

This is deliberately incomplete. Reject unsupported operations explicitly.
"""
import copy
import functools
import json
import re
import sys


class CompileError(Exception):
    pass


class RuntimeErrorJq(Exception):
    pass


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
            node = ('literal', json.loads(value))
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
    if type(value) in (int, float):
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
    if left_type in (3, 4):
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


def validate_variables(node, names):
    kind = node[0]
    if kind == 'variable':
        if node[1] not in names:
            raise CompileError('$' + node[1] + ' is not defined')
    elif kind == 'bind':
        validate_variables(node[1], names)
        validate_variables(node[3], names | pattern_names(node[2]))
    elif kind in ('reduce', 'foreach'):
        validate_variables(node[1], names)
        validate_variables(node[3], names)
        scope = names | pattern_names(node[2])
        validate_variables(node[4], scope)
        if node[5] is not None:
            validate_variables(node[5], scope)
    elif kind in ('array', 'negate', 'field', 'iterate'):
        validate_variables(node[1], names)
    elif kind in ('pipe', 'comma', 'index', 'try'):
        validate_variables(node[1], names)
        validate_variables(node[2], names)
    elif kind in ('binary', 'assignment'):
        validate_variables(node[2], names)
        validate_variables(node[3], names)
    elif kind == 'if':
        for child in node[1:]:
            validate_variables(child, names)
    elif kind == 'object':
        for _, child in node[1]:
            validate_variables(child, names)
    elif kind == 'call' and node[2] is not None:
        validate_variables(node[2], names)


def values(node, value, variables):
    kind = node[0]
    if kind == 'identity':
        yield value
    elif kind == 'literal':
        yield node[1]
    elif kind == 'negate':
        for item in values(node[1], value, variables):
            if type(item) not in (int, float):
                raise RuntimeErrorJq('cannot negate this value')
            yield -item
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
                elif op in ('-', '*'):
                    if type(left_value) not in (int, float) or type(right_value) not in (int, float):
                        raise RuntimeErrorJq('incompatible numeric operands')
                    yield left_value - right_value if op == '-' else left_value * right_value
                elif op in ('==', '!='):
                    equal = compare_values(left_value, right_value) == 0
                    yield equal if op == '==' else not equal
                else:
                    comparison = compare_values(left_value, right_value)
                    yield {'>': comparison > 0, '<': comparison < 0,
                           '>=': comparison >= 0, '<=': comparison <= 0}[op]
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
        elif name == 'sort' and argument is None:
            if not isinstance(value, list):
                raise RuntimeErrorJq('sort requires an array')
            yield sorted(value, key=functools.cmp_to_key(compare_values))
        elif name != 'empty':
            raise CompileError('unknown or unsupported filter ' + name)
    else:
        raise CompileError('unsupported expression')


_MISSING = object()


def parse_json_values(chunks):
    decoder = json.JSONDecoder()
    chunks = iter(chunks)
    pending = ''
    exhausted = False
    while True:
        pending = pending.lstrip()
        if not pending and exhausted:
            return
        if not pending:
            try:
                pending += next(chunks)
            except StopIteration:
                exhausted = True
            continue
        try:
            item, end = decoder.raw_decode(pending)
        except ValueError as exc:
            if exhausted:
                raise RuntimeErrorJq('invalid JSON input: ' + str(exc)) from exc
            try:
                pending += next(chunks)
            except StopIteration:
                exhausted = True
            continue
        scalar = item is None or type(item) in (bool, int, float)
        if scalar and end == len(pending) and not exhausted:
            try:
                pending += next(chunks)
            except StopIteration:
                exhausted = True
            continue
        if scalar and end < len(pending) and not (pending[end].isspace() or pending[end] in '[{"'):
            raise RuntimeErrorJq('invalid JSON literal')
        yield item
        pending = pending[end:]


class InputStream:
    """One shared input cursor for automatic iteration and input/inputs."""

    def __init__(self, paths, raw_mode, slurp):
        self.paths = paths or ['-']
        self.raw_mode = raw_mode
        self.slurp = slurp
        self.file_error = False

    def chunks(self):
        for path in self.paths:
            if path == '-':
                yield sys.stdin.read()
            else:
                try:
                    with open(path, encoding='utf-8', errors='replace', newline='') as source:
                        yield source.read()
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
        elif self.slurp:
            yield list(parse_json_values(self.chunks()))
        else:
            yield from parse_json_values(self.chunks())


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
            elif option == '--raw-output0':
                flags.add('raw-output0')
            elif option.startswith('--') or any(c not in 'nscerR' for c in option[1:]):
                raise CompileError('unsupported option ' + option)
            else:
                flags.update(option[1:])
        if not argv:
            raise CompileError('expected one filter')
        program = Parser(argv.pop(0)).parse()
        validate_variables(program, set(variables))
        input_stream = InputStream(argv, 'R' in flags, 's' in flags)
        cursor = iter(input_stream)
        variables['@inputs'] = cursor
        source = [None] if 'n' in flags else cursor
        output_count = 0
        last = None
        for item in source:
            for result in values(program, item, variables):
                output_count += 1
                last = result
                if ('r' in flags or 'raw-output0' in flags) and isinstance(result, str):
                    if 'raw-output0' in flags and '\0' in result:
                        raise RuntimeErrorJq('cannot output string containing NUL with --raw-output0')
                    output = result
                else:
                    output = json.dumps(result, ensure_ascii=False, separators=(',', ':') if 'c' in flags else None,
                                        indent=None if 'c' in flags else 2)
                sys.stdout.write(output + ('\0' if 'raw-output0' in flags else '\n'))
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
