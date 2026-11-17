"""The language a driver's trigger is written in (owner, 16-17 Nov 2026; docs/design/21_risk_site.md, "Driver rules").

A trigger says when a driver is on. It is a Python-style test, as the owner's risk engine writes it. Real examples:

    to_int(get('RD65')) >= 1
    get(RD22) > 1.5 * prevailing(RD22)
    (get(RD35) == 'Broadly used, across teams')
    (get('RD01') == True) and not get('RD02')
    'Option A' in get('RD40')
    3 <= get('RD70') <= 10

Nothing is ever run as code. There is no eval, exec or compile-to-run here. The steps are:

    1. tidy_text         fix what Python can't read but the owner's files use (curly quotes, &&, ||, !, AND, TRUE, null)
    2. ast.parse         Python's own reader turns the text into a tree (it only reads, it does not run anything)
    3. TriggerReader     walks that tree with an allow-list; any piece not on the list is a plain-words problem
    4. evaluate          our own walk over the small tree below gives True, False or "not known"

The tree is made of plain tuples; the first item says what it is:

    ("number", 3.0)   ("text", "Broadly used")   ("yes_no", True)   ("none",)   ("list", [constant, ...])
    ("call", "get", [("text", "RD22")])           get(RD22). A bare code is read as text. Codes are upper case.
    ("call", name, [argument, ...])               prevailing, to_int, to_float, int, float, str, bool, len, abs, min, max, round
    ("method", "lower", target, [argument, ...])  text methods: lower upper strip title startswith endswith
    ("math", "+", a, b)   ("minus", x)            + - * / % with numbers
    ("not", x)   ("and", a, b)   ("or", a, b)
    ("compare", sign, a, b)                       sign is == != < <= > >= in, not in, is, is not, selected, not selected

A chained test (3 <= x <= 10) is read as two comparisons joined by "and".
"X in get(RD40)" is "selected": X is one of the options ticked in the answer (see option_selected).
"""
import ast
import math
import re
import warnings

LONGEST_TRIGGER = 2000                                   # characters; a real trigger is about 20 to 80
MOST_NESTING = 100                                       # how deep the tree may go
MOST_PIECES_JOINED = 100                                 # tests joined by one and / or
NONE_OF_THESE = "None of these"                          # the tick-any question's "nothing ticked" option

# The functions, and the fewest and most values each takes.
FUNCTIONS = {"get": (1, 2), "prevailing": (1, 1), "to_int": (1, 1), "to_float": (1, 1), "int": (1, 1), "float": (1, 1),
             "str": (1, 1), "bool": (1, 1), "len": (1, 1), "abs": (1, 1), "min": (2, 6), "max": (2, 6), "round": (1, 2)}
FUNCTION_ALIASES = {"prevailing_median": "prevailing"}
CODE_FUNCTIONS = ("get", "prevailing")                   # these take an answer's code, quoted or not
NUMBER_FUNCTIONS = ("to_int", "to_float", "int", "float", "abs", "round", "min", "max", "len", "prevailing")
TEXT_METHODS = {"lower": (0, 0), "upper": (0, 0), "strip": (0, 0), "title": (0, 0), "startswith": (1, 1), "endswith": (1, 1)}
CONSTANT_KINDS = ("number", "text", "yes_no", "none")

COMPARE_SIGNS = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}
MATH_SIGNS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%"}

NUMBER_AT_START = re.compile(r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
WORD_AT_START = re.compile(r"[A-Za-z_]\w*")
CODE_PATTERN = re.compile(r"^\w+$")
WORD_FOR = {"and": " and ", "or": " or ", "not": " not ", "true": "True", "false": "False", "none": "None", "null": "None"}
QUOTE_CLOSERS = {"'": "'", '"': '"', "\u201c": "\u201c\u201d\"", "\u201d": "\u201c\u201d\"", "\u2018": "\u2018\u2019'", "\u2019": "\u2018\u2019'"}

YES_WORDS = {"true", "yes", "y", "1"}
NO_WORDS = {"false", "no", "n", "0"}


class TriggerProblem(ValueError):
    """A trigger that can't be read. The message is a plain sentence that names the place."""


def problem_at(position, shown, reason):
    """The one sentence every reading problem uses. position is 0-based; the sentence counts characters from 1."""
    if shown is None:
        return TriggerProblem(f"Can't read the trigger at its end (after character {position}): {reason}")
    return TriggerProblem(f"Can't read the trigger near character {position + 1} ({shown!r}): {reason}")


# ---------------------------------------------------------------------------------------------------
# Step 1: tidy only what Python can't read
# ---------------------------------------------------------------------------------------------------

def tidy_text(text):
    """(tidy text, where each tidy character came from in the original). Quotes made straight, && || ! AND OR NOT
    TRUE FALSE NONE null made into Python words, a # comment dropped. Text inside quotes is never changed."""
    pieces = []
    origins = []

    def put(piece, at):
        pieces.append(piece)
        origins.extend([at] * len(piece))

    position = 0
    while position < len(text):
        character = text[position]
        rest = text[position:]
        if character in QUOTE_CLOSERS:
            closers = QUOTE_CLOSERS[character]
            is_straight = character in "'\""
            end = position + 1
            while end < len(text) and text[end] not in closers:
                end += 2 if (is_straight and text[end] == "\\") else 1
            if end >= len(text):
                raise problem_at(position, text[position:position + 12], "the quote is never closed.")
            if is_straight:
                literal = text[position:end + 1].replace("\n", "\\n").replace("\r", "\\r")
            else:
                literal = repr(text[position + 1:end])
            put(" " + literal + " ", position)
            position = end + 1
        elif character == "#":
            while position < len(text) and text[position] != "\n":
                position += 1
        elif character.isspace():
            put(" ", position)
            position += 1
        elif rest.startswith("&&"):
            put(" and ", position)
            position += 2
        elif rest.startswith("||"):
            put(" or ", position)
            position += 2
        elif character == "!" and not rest.startswith("!="):
            put(" not ", position)
            position += 1
        elif NUMBER_AT_START.match(rest):
            number = NUMBER_AT_START.match(rest).group()
            put(number, position)
            position += len(number)
        elif WORD_AT_START.match(rest):
            word = WORD_AT_START.match(rest).group()
            after_a_dot = position > 0 and text[position - 1] == "."
            put(word if after_a_dot else WORD_FOR.get(word.lower(), word), position)
            position += len(word)
        else:
            put(character, position)
            position += 1
    return "".join(pieces), origins


# ---------------------------------------------------------------------------------------------------
# Steps 2 and 3: Python reads the text, we walk what it found
# ---------------------------------------------------------------------------------------------------

REASON_FOR_NODE = {
    ast.Lambda: "a lambda is not allowed in a trigger.",
    ast.ListComp: "loops and list building are not allowed in a trigger.",
    ast.SetComp: "loops and set building are not allowed in a trigger.",
    ast.DictComp: "loops and dictionary building are not allowed in a trigger.",
    ast.GeneratorExp: "loops are not allowed in a trigger.",
    ast.JoinedStr: "f-strings are not allowed in a trigger.",
    ast.FormattedValue: "f-strings are not allowed in a trigger.",
    ast.Subscript: "square-bracket lookups like x[0] are not allowed. A list of texts is only allowed after in, like get('RD01') in ['A', 'B'].",
    ast.Attribute: "only these text methods are allowed: .lower() .upper() .strip() .title() .startswith(x) .endswith(x).",
    ast.IfExp: "if ... else ... is not allowed in a trigger. Use and, or, not.",
    ast.NamedExpr: "assignments are not allowed in a trigger.",
    ast.Dict: "dictionaries are not allowed in a trigger.",
    ast.Set: "sets are not allowed in a trigger.",
    ast.Await: "this is not allowed in a trigger.",
    ast.Yield: "this is not allowed in a trigger.",
    ast.Starred: "a star in front of a value is not allowed in a trigger.",
}


class TriggerReader:
    """Walks the tree Python made and builds our small tuple tree. Only the node types handled here are allowed."""

    def __init__(self, tidy, origins):
        self.tidy = tidy
        self.origins = origins

    def refuse(self, node, reason):
        offset = getattr(node, "col_offset", 0)
        position = self.origins[offset] if offset < len(self.origins) else len(self.origins)
        shown = (ast.get_source_segment(self.tidy, node) or "").strip()[:40]
        raise problem_at(position, shown or None, reason)

    def read(self, node, depth=0):
        if depth > MOST_NESTING:
            raise TriggerProblem("The trigger is nested too deeply to read. Make it simpler.")
        if isinstance(node, ast.Expression):
            return self.read(node.body, depth)
        if isinstance(node, ast.Constant):
            return self.constant(node)
        if isinstance(node, ast.BoolOp):
            return self.bool_operation(node, depth)
        if isinstance(node, ast.UnaryOp):
            return self.unary(node, depth)
        if isinstance(node, ast.BinOp):
            return self.binary(node, depth)
        if isinstance(node, ast.Compare):
            return self.comparison(node, depth)
        if isinstance(node, ast.Call):
            return self.call(node, depth)
        if isinstance(node, ast.Name):
            self.refuse(node, "text must be in quotes, for example 'Broadly used'. A code is only written inside get(...) or prevailing(...).")
        if isinstance(node, (ast.List, ast.Tuple)):
            self.refuse(node, "a list of values is only allowed after in or not in, like get('RD01') in ['A', 'B'].")
        reason = REASON_FOR_NODE.get(type(node), "this kind of expression is not allowed in a trigger.")
        self.refuse(node, reason)

    def constant(self, node):
        value = node.value
        if isinstance(value, bool):
            return ("yes_no", value)
        if value is None:
            return ("none",)
        if isinstance(value, str):
            return ("text", value)
        if isinstance(value, (int, float)) and math.isfinite(value):
            return ("number", float(value))
        self.refuse(node, "only numbers, quoted text, True, False and None can be written as plain values.")

    def bool_operation(self, node, depth):
        joined = "and" if isinstance(node.op, ast.And) else "or"
        if len(node.values) > MOST_PIECES_JOINED:
            self.refuse(node, f"more than {MOST_PIECES_JOINED} tests are joined by {joined}. Make it simpler.")
        parts = [self.read(value, depth + len(node.values)) for value in node.values]
        tree = parts[0]
        for part in parts[1:]:
            tree = (joined, tree, part)
        return tree

    def unary(self, node, depth):
        if isinstance(node.op, ast.Not):
            return ("not", self.read(node.operand, depth + 1))
        if isinstance(node.op, (ast.USub, ast.UAdd)):
            operand = self.read(node.operand, depth + 1)
            if isinstance(node.op, ast.UAdd):
                return operand
            if operand[0] == "number":
                return ("number", -operand[1])
            return ("minus", operand)
        self.refuse(node, "this sign is not allowed in a trigger.")

    def binary(self, node, depth):
        left = self.read(node.left, depth + 1)
        right = self.read(node.right, depth + 1)
        if isinstance(node.op, ast.BitAnd):
            return ("and", left, right)
        if isinstance(node.op, ast.BitOr):
            return ("or", left, right)
        sign = MATH_SIGNS.get(type(node.op))
        if sign is None:
            self.refuse(node, "only + - * / % are allowed between numbers.")
        return ("math", sign, left, right)

    def comparison(self, node, depth):
        operands = [self.read(node.left, depth + len(node.ops))]
        tests = []
        for operator, comparator in zip(node.ops, node.comparators):
            before = operands[-1]
            after = self.right_side(operator, comparator, node, depth + len(node.ops))
            tests.append(self.one_comparison(operator, before, after, node))
            operands.append(after)
        tree = tests[0]
        for test in tests[1:]:
            tree = ("and", tree, test)
        return tree

    def right_side(self, operator, comparator, node, depth):
        """The right side of a comparison. After in / not in, a list or tuple of plain values is allowed."""
        if isinstance(operator, (ast.In, ast.NotIn)) and isinstance(comparator, (ast.List, ast.Tuple)):
            items = [self.read(item, depth + 1) for item in comparator.elts]
            if any(item[0] not in CONSTANT_KINDS for item in items):
                self.refuse(comparator, "a list after in must hold only numbers, quoted text, True, False or None.")
            return ("list", items)
        return self.read(comparator, depth + 1)

    def one_comparison(self, operator, left, right, node):
        if type(operator) in COMPARE_SIGNS:
            return ("compare", COMPARE_SIGNS[type(operator)], left, right)
        if isinstance(operator, (ast.Is, ast.IsNot)):
            if right[0] not in ("none", "yes_no"):
                self.refuse(node, "is and is not can only be used with None, True or False. Use == to compare with a number or text.")
            return ("compare", "is" if isinstance(operator, ast.Is) else "is not", left, right)
        negated = isinstance(operator, ast.NotIn)
        if right[0] in ("list", "text"):
            return ("compare", "not in" if negated else "in", left, right)
        return ("compare", "not selected" if negated else "selected", left, right)

    def call(self, node, depth):
        if node.keywords or any(isinstance(argument, ast.Starred) for argument in node.args):
            self.refuse(node, "values can't be given by name or with a star here.")
        if isinstance(node.func, ast.Attribute):
            return self.method(node, depth)
        if not isinstance(node.func, ast.Name):
            self.refuse(node, "only the functions named below can be used in a trigger.")
        name = node.func.id.lower()
        name = FUNCTION_ALIASES.get(name, name)
        if name not in FUNCTIONS:
            names = ", ".join(sorted(FUNCTIONS) + sorted(FUNCTION_ALIASES))
            self.refuse(node.func, f"'{node.func.id}' is not a function this language has. The functions are {names}.")
        fewest, most = FUNCTIONS[name]
        if not fewest <= len(node.args) <= most:
            takes = f"{fewest}" if fewest == most else f"{fewest} to {most}"
            self.refuse(node, f"{name}(...) takes {takes} value{'s' if most > 1 else ''}, and was given {len(node.args)}.")
        if name in CODE_FUNCTIONS:
            arguments = [self.code_argument(name, node.args[0])]
            if len(node.args) == 2:
                default = self.read(node.args[1], depth + 1)
                if default[0] not in CONSTANT_KINDS:
                    self.refuse(node.args[1], f"the second value of {name}(...) is what to use when there is no answer: a number, quoted text, True, False or None.")
                arguments.append(default)
            return ("call", name, arguments)
        return ("call", name, [self.read(argument, depth + 1) for argument in node.args])

    def code_argument(self, function, node):
        """get and prevailing take an answer's code, with or without quotes: get(RD22) or get('RD22')."""
        if isinstance(node, ast.Name):
            code = node.id
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            code = node.value.strip()
        else:
            self.refuse(node, f"{function}(...) needs a code such as RD01, with or without quotes.")
        if not CODE_PATTERN.match(code):
            self.refuse(node, f"{function}(...) needs a code such as RD01, with or without quotes.")
        return ("text", code.upper())

    def method(self, node, depth):
        name = node.func.attr
        if name not in TEXT_METHODS:
            self.refuse(node.func, REASON_FOR_NODE[ast.Attribute])
        fewest, most = TEXT_METHODS[name]
        if not fewest <= len(node.args) <= most:
            self.refuse(node, f".{name}(...) takes {most} value{'' if most == 1 else 's'}, and was given {len(node.args)}.")
        target = self.read(node.func.value, depth + 1)
        return ("method", name, target, [self.read(argument, depth + 1) for argument in node.args])


def syntax_problem(problem, text, tidy, origins):
    """A plain sentence for a trigger Python could not read."""
    offset = (problem.offset or 0) - 1
    past_the_end = offset < 0 or offset >= len(tidy.rstrip())
    message = problem.msg or ""
    single_equals = 0 <= offset < len(tidy) and tidy[offset] == "=" and tidy[offset:offset + 2] != "=="
    if single_equals or "Maybe you meant '=='" in message or "cannot assign" in message:
        reason = "use == to compare two things (a single = is not used)."
    elif "never closed" in message or "was never closed" in message:
        reason = "a bracket was opened and not closed. Add a closing bracket."
    elif "unmatched" in message:
        reason = "a closing bracket has no opening bracket before it."
    elif "too many nested" in message:
        reason = "the brackets are nested too deeply. Make it simpler."
    elif past_the_end:
        reason = "the trigger stops where a value was expected."
    else:
        reason = "this does not fit after what came before it. Join two tests with and, or, and put a value on both sides of each comparison."
    if past_the_end:
        return problem_at(len(text), None, reason)
    position = origins[min(offset, len(origins) - 1)]
    return problem_at(position, text[position:position + 12].strip() or text[position], reason)


def read_trigger(text):
    """The trigger as a tree. Raises TriggerProblem (a ValueError) with a plain sentence when it can't be read, or
    when it looks at no answer at all. Nothing in the text is ever run."""
    shown = "" if text is None else str(text)
    if not shown.strip():
        raise TriggerProblem("The trigger is empty.")
    if len(shown) > LONGEST_TRIGGER:
        raise TriggerProblem(f"The trigger is longer than {LONGEST_TRIGGER} characters, so it was not read.")
    tidy, origins = tidy_text(shown)
    if not tidy.strip():
        raise TriggerProblem("The trigger is empty.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = ast.parse(tidy.strip(), mode="eval")
    except SyntaxError as problem:
        raise syntax_problem(problem, shown, tidy.strip(), origins[len(tidy) - len(tidy.lstrip()):]) from None
    except (RecursionError, MemoryError):
        raise TriggerProblem("The trigger is nested too deeply to read. Make it simpler.") from None
    except ValueError:
        raise TriggerProblem("The trigger has a character that can't be read.") from None
    stripped_start = len(tidy) - len(tidy.lstrip())
    reader = TriggerReader(tidy.strip(), origins[stripped_start:])
    try:
        tree = reader.read(parsed)
    except RecursionError:
        raise TriggerProblem("The trigger is nested too deeply to read. Make it simpler.") from None
    if not fields_used(tree):
        raise TriggerProblem("The trigger doesn't look at any answer. Use get('RD01') to look at an answer.")
    return tree


# ---------------------------------------------------------------------------------------------------
# Walking a tree: which answers it uses
# ---------------------------------------------------------------------------------------------------

def children_of(tree):
    kind = tree[0]
    if kind == "call":
        return list(tree[2])
    if kind == "method":
        return [tree[2]] + list(tree[3])
    if kind == "list":
        return list(tree[1])
    if kind in ("not", "minus"):
        return [tree[1]]
    if kind in ("and", "or"):
        return [tree[1], tree[2]]
    if kind in ("compare", "math"):
        return [tree[2], tree[3]]
    return []


def calls_to(tree, function):
    """The codes given to one function anywhere in the tree, in the order written: calls_to(tree, "get")."""
    found = []
    if tree[0] == "call" and tree[1] == function:
        found.append(tree[2][0][1])
    for child in children_of(tree):
        found.extend(calls_to(child, function))
    return found


def codes_without_a_fallback(tree):
    """The codes given to get() with no second value (no fallback for a missing answer)."""
    found = []
    if tree[0] == "call" and tree[1] == "get" and len(tree[2]) == 1:
        found.append(tree[2][0][1])
    for child in children_of(tree):
        found.extend(codes_without_a_fallback(child))
    return found


def fields_used(tree):
    """The set of codes passed to get()."""
    return set(calls_to(tree, "get"))


def fields_in_order(tree):
    """The codes passed to get(), in the order written, each once."""
    seen = []
    for code in calls_to(tree, "get"):
        if code not in seen:
            seen.append(code)
    return seen


def how_fields_are_used(tree):
    """What each answer is compared with:
    {code: {"text": [choices], "tick_any": [options], "yes_no": True or False, "number": True or False}}.
    The form uses this to choose the kind of question. A field compared with text gets those texts as its (single)
    choices; a field used as 'X' in get(code) is tick-any, and each X is one of its options."""
    uses = {code: {"text": [], "tick_any": [], "yes_no": False, "number": False} for code in fields_in_order(tree)}
    _note_uses(tree, uses)
    return uses


def _answer_looked_at(side):
    """(code, wrapped_in_a_number_function) when this side is get(code), maybe inside to_int(...), .lower() and the like;
    else None."""
    if side[0] == "call" and side[1] == "get":
        return side[2][0][1], False
    if side[0] == "call" and side[1] in ("to_int", "to_float", "int", "float", "abs", "round"):
        inner = _answer_looked_at(side[2][0])
        return (inner[0], True) if inner else None
    if side[0] == "call" and side[1] == "str":
        return _answer_looked_at(side[2][0])
    if side[0] == "method" and side[1] in ("lower", "upper", "strip", "title"):
        return _answer_looked_at(side[2])
    return None


def _is_number_like(side):
    return side[0] in ("number", "math", "minus") or (side[0] == "call" and side[1] in NUMBER_FUNCTIONS)


def _note_one_choice(uses, code, other, as_number):
    if as_number or _is_number_like(other):
        uses[code]["number"] = True
    elif other[0] == "text":
        if other[1] not in uses[code]["text"]:
            uses[code]["text"].append(other[1])
    elif other[0] == "yes_no":
        uses[code]["yes_no"] = True


def _note_uses(tree, uses):
    kind = tree[0]
    if kind == "compare":
        sign, left, right = tree[1], tree[2], tree[3]
        if sign in ("selected", "not selected"):
            looked_at = _answer_looked_at(right)
            if looked_at and left[0] == "text" and left[1] not in uses[looked_at[0]]["tick_any"]:
                uses[looked_at[0]]["tick_any"].append(left[1])
            return
        if sign in ("in", "not in"):
            looked_at = _answer_looked_at(left)
            if looked_at is None:
                return
            code, as_number = looked_at
            if right[0] == "list":
                for item in right[1]:
                    _note_one_choice(uses, code, item, as_number)
            return
        if sign in ("is", "is not"):
            looked_at = _answer_looked_at(left)
            if looked_at and right[0] == "yes_no":
                uses[looked_at[0]]["yes_no"] = True
            return
        for side, other in ((left, right), (right, left)):
            looked_at = _answer_looked_at(side)
            if looked_at is not None:
                _note_one_choice(uses, looked_at[0], other, looked_at[1])
            elif side[0] in ("math", "minus") or (side[0] == "call" and side[1] in NUMBER_FUNCTIONS and side[1] != "prevailing"):
                for code in fields_in_order(side):
                    uses[code]["number"] = True
        return
    if kind == "call" and tree[1] == "get":
        uses[tree[2][0][1]]["yes_no"] = True              # get(code) on its own is a yes or no
        return
    if kind in ("and", "or", "not"):
        for child in children_of(tree):
            _note_uses(child, uses)


# ---------------------------------------------------------------------------------------------------
# Step 4: working out true or false
# ---------------------------------------------------------------------------------------------------

def is_missing(value):
    """No answer: nothing, blank text, or a list with nothing ticked."""
    if isinstance(value, (list, tuple, set)):
        return len(value) == 0
    return value is None or (isinstance(value, str) and value.strip() == "")


def as_yes_no(value):
    """True or False for a yes or no, None when the value is neither."""
    if isinstance(value, bool):
        return value
    if is_missing(value):
        return None
    word = str(value).strip().lower()
    if word in YES_WORDS:
        return True
    if word in NO_WORDS:
        return False
    return None


def as_number(value):
    """The value as a number, or None. "1,200" is 1200 and "25%" is 0.25, as the rest of the Risk site reads them."""
    if is_missing(value) or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    text = str(value).strip().replace(",", "")
    is_percent = text.endswith("%")
    try:
        number = float(text.rstrip("%").strip())
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number / 100 if is_percent else number


def to_int(value):
    """A whole number from an answer. Missing or not a number is 0; yes is 1; 3.9 is 3."""
    if isinstance(value, bool):
        return 1 if value else 0
    number = as_number(value)
    return 0 if number is None else int(number)


def to_float(value):
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    number = as_number(value)
    return 0.0 if number is None else number


def plain_text(value):
    """Text as it is compared: no capitals, no spaces at either end."""
    return str(value).strip().lower()


def as_truth(value):
    """A value standing alone as a condition (get('RD01'), or the part of an and / or / not). Yes words are true,
    no words and missing are false, any other number is true unless it is 0, other text is false."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (list, tuple, set)):
        return any(plain_text(item) != plain_text(NONE_OF_THESE) for item in value)
    yes_no = as_yes_no(value)
    if yes_no is not None:
        return yes_no
    number = as_number(value)
    return number != 0 if number is not None else False


def selected_options(answer):
    """The options an answer says were chosen, in plain form (no capitals, no outer spaces). A list answer is its
    items. A single text is the whole text, plus each item when it holds commas or semicolons: "Yes; No" is two."""
    if isinstance(answer, (list, tuple, set)):
        return [plain_text(item) for item in answer if not is_missing(item)]
    whole = plain_text(answer)
    items = [plain_text(item) for item in re.split(r"[,;]", str(answer)) if item.strip()]
    return [whole] + items


def option_selected(option, answer):
    """True when the option is one of those chosen in the answer, False when not, None when the answer is missing.
    'Yes' is in "Yes, partly" because "Yes" is one of its items; 'es' is not (no part-word matching)."""
    if is_missing(answer) or is_missing(option):
        return None
    return plain_text(option) in selected_options(answer)


def compare(sign, left, right):
    """One comparison. Comparing with a missing answer is False (never an error), except None == None.
    A list answer (several options ticked) equals an option when that option is one of them."""
    if isinstance(left, (list, tuple, set)):
        found = option_selected(right, left)
        if found is None:
            return False
        return found if sign == "==" else (not found if sign == "!=" else False)
    if left is None and right is None:
        return sign in ("==", ">=", "<=")
    if left is None or right is None:
        return False
    if isinstance(left, bool) or isinstance(right, bool):
        left_yes, right_yes = as_yes_no(left), as_yes_no(right)
        if left_yes is None or right_yes is None:
            return False
        return _by_sign(sign, left_yes, right_yes)
    left_number, right_number = as_number(left), as_number(right)
    if left_number is not None and right_number is not None:
        return _by_sign(sign, left_number, right_number)
    if sign in ("==", "!="):
        return _by_sign(sign, plain_text(left), plain_text(right))
    if isinstance(left, (int, float)) or isinstance(right, (int, float)):
        return False                                      # a number and a word can't be put in order
    return _by_sign(sign, plain_text(left), plain_text(right))


def _by_sign(sign, left, right):
    if sign == "==":
        return left == right
    if sign == "!=":
        return left != right
    if sign == ">=":
        return left >= right
    if sign == "<=":
        return left <= right
    if sign == ">":
        return left > right
    return left < right


def evaluate(tree, answer_of, prevailing_of=None):
    """True or False for one team.

    answer_of(code)      the team's answer: True or False for a yes or no, a number, text, a list of ticked options,
                         or None when missing
    prevailing_of(code)  the prevailing median for a data field, or None
    """
    value = _value_of(tree, answer_of, prevailing_of or (lambda code: None))
    return as_truth(value)


def _value_of(tree, answer_of, prevailing_of):
    kind = tree[0]
    if kind in ("number", "text", "yes_no"):
        return tree[1]
    if kind == "none":
        return None
    if kind == "list":
        return [_value_of(item, answer_of, prevailing_of) for item in tree[1]]
    if kind == "not":
        return not as_truth(_value_of(tree[1], answer_of, prevailing_of))
    if kind == "and":
        return as_truth(_value_of(tree[1], answer_of, prevailing_of)) and as_truth(_value_of(tree[2], answer_of, prevailing_of))
    if kind == "or":
        return as_truth(_value_of(tree[1], answer_of, prevailing_of)) or as_truth(_value_of(tree[2], answer_of, prevailing_of))
    if kind == "minus":
        number = as_number(_value_of(tree[1], answer_of, prevailing_of))
        return None if number is None else -number
    if kind == "math":
        return _math_value(tree[1], _value_of(tree[2], answer_of, prevailing_of), _value_of(tree[3], answer_of, prevailing_of))
    if kind == "compare":
        return _comparison_value(tree, answer_of, prevailing_of)
    if kind == "method":
        return _method_value(tree, answer_of, prevailing_of)
    return _call_value(tree, answer_of, prevailing_of)


def _math_value(sign, left, right):
    """+ - * / % on two numbers. Not a number, or dividing by zero, is not known (None)."""
    left_number, right_number = as_number(left), as_number(right)
    if left_number is None or right_number is None:
        return None
    if sign in ("/", "%") and right_number == 0:
        return None
    if sign == "+":
        result = left_number + right_number
    elif sign == "-":
        result = left_number - right_number
    elif sign == "*":
        result = left_number * right_number
    elif sign == "/":
        result = left_number / right_number
    else:
        result = left_number % right_number
    return result if math.isfinite(result) else None


def _comparison_value(tree, answer_of, prevailing_of):
    sign, left_tree, right_tree = tree[1], tree[2], tree[3]
    left = _value_of(left_tree, answer_of, prevailing_of)
    right = _value_of(right_tree, answer_of, prevailing_of)
    if sign in ("selected", "not selected"):
        found = option_selected(left, right)
        if found is None:
            return False                                  # no answer: not known, so not true either way
        return found if sign == "selected" else not found
    if sign in ("in", "not in"):
        if is_missing(left):
            return False
        if isinstance(right, list):
            wanted = left if isinstance(left, (list, tuple, set)) else [left]
            found = any(compare("==", one, item) for one in wanted for item in right)
        else:
            found = isinstance(left, str) and plain_text(left) in plain_text(right)
        return found if sign == "in" else not found
    if sign in ("is", "is not"):
        if right is None:
            return (left is None) if sign == "is" else (left is not None)
        if is_missing(left):
            return False
        same = as_yes_no(left) is right
        return same if sign == "is" else not same
    if left_tree[0] == "none" or right_tree[0] == "none":
        other_is_missing = (right if left_tree[0] == "none" else left) is None
        return other_is_missing if sign == "==" else (not other_is_missing if sign == "!=" else False)
    return compare(sign, left, right)


def _method_value(tree, answer_of, prevailing_of):
    """A text method on text. On anything else (a number, a missing answer) it is not known (None)."""
    name = tree[1]
    target = _value_of(tree[2], answer_of, prevailing_of)
    if not isinstance(target, str):
        return None
    if name == "lower":
        return target.lower()
    if name == "upper":
        return target.upper()
    if name == "strip":
        return target.strip()
    if name == "title":
        return target.title()
    argument = _value_of(tree[3][0], answer_of, prevailing_of)
    if not isinstance(argument, str):
        return None
    return target.startswith(argument) if name == "startswith" else target.endswith(argument)


def _call_value(tree, answer_of, prevailing_of):
    function, arguments = tree[1], tree[2]
    if function == "get":
        answer = answer_of(arguments[0][1])
        if is_missing(answer):
            return arguments[1][1] if len(arguments) == 2 else None
        return answer
    if function == "prevailing":
        return as_number(prevailing_of(arguments[0][1]))
    values = [_value_of(argument, answer_of, prevailing_of) for argument in arguments]
    first = values[0]
    if function == "str":
        return _as_plain_string(first)
    if function == "bool":
        return None if is_missing(first) else as_truth(first)
    if function == "len":
        return float(len(first)) if isinstance(first, str) else None
    numbers = [as_number(value) for value in values]
    if any(number is None for number in numbers):
        return None                                       # missing, or text that is not a number: not known
    if function in ("to_int", "int"):
        return float(int(numbers[0]))
    if function in ("to_float", "float"):
        return numbers[0]
    if function == "abs":
        return abs(numbers[0])
    if function == "min":
        return min(numbers)
    if function == "max":
        return max(numbers)
    digits = int(numbers[1]) if len(numbers) == 2 else 0
    return float(round(numbers[0], digits))


def _as_plain_string(value):
    if is_missing(value):
        return None
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return str(int(value)) if value == int(value) else str(value)
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item) for item in value)
    return str(value)


def evaluate_or_unknown(tree, answer_of, prevailing_of=None):
    """True or False, or None when it can't be told: every answer the trigger asks for is missing (an answer with a
    fallback, get('RD70', 0), doesn't count), or a prevailing median it needs isn't there. A driver that can't be told
    is never counted as on."""
    prevailing_of = prevailing_of or (lambda code: None)
    asked_for = set(codes_without_a_fallback(tree))
    if asked_for and all(is_missing(answer_of(code)) for code in asked_for):
        return None
    if any(prevailing_of(code) is None for code in calls_to(tree, "prevailing")):
        return None
    return evaluate(tree, answer_of, prevailing_of)


# ---------------------------------------------------------------------------------------------------
# Writing it back
# ---------------------------------------------------------------------------------------------------

def to_text(tree):
    """The trigger in one tidy form. A comparison is in brackets: (get('RD01') == True). Examples:
        (get('RD12') >= 3)      (get('RD01') == True) and not (get('RD02') == True)      to_int(get('RD65'))"""
    return _written(tree, inside_a_join=False)


def _written_text(text):
    escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return f"'{escaped}'"


def _written(tree, inside_a_join):
    kind = tree[0]
    if kind == "number":
        number = tree[1]
        return str(int(number)) if number == int(number) else repr(number)
    if kind == "text":
        return _written_text(tree[1])
    if kind == "yes_no":
        return "True" if tree[1] else "False"
    if kind == "none":
        return "None"
    if kind == "list":
        return "[" + ", ".join(_written(item, False) for item in tree[1]) + "]"
    if kind == "call":
        return f"{tree[1]}({', '.join(_written(argument, False) for argument in tree[2])})"
    if kind == "method":
        return f"{_written(tree[2], False)}.{tree[1]}({', '.join(_written(argument, False) for argument in tree[3])})"
    if kind == "minus":
        return f"-{_written(tree[1], True)}"
    if kind == "math":
        return f"({_written(tree[2], False)} {tree[1]} {_written(tree[3], False)})"
    if kind == "compare":
        sign = tree[1]
        if sign == "selected":
            return f"({_written(tree[2], False)} in {_written(tree[3], False)})"
        if sign == "not selected":
            return f"({_written(tree[2], False)} not in {_written(tree[3], False)})"
        return f"({_written(tree[2], False)} {sign} {_written(tree[3], False)})"
    if kind == "not":
        inner = _written(tree[1], True)
        return f"not {inner}"
    joiner = f" {kind} "
    joined = _written(tree[1], True) + joiner + _written(tree[2], True)
    return f"({joined})" if inside_a_join else joined
