"""The small language a driver's trigger is written in (owner, 16 Nov 2026; docs/design/21_risk_site.md, "Driver rules").

A trigger says when a driver is on. Real examples from the owner's driver_mapping.yaml:

    to_int(get('RD65')) >= 1
    get(RD22) > prevailing(RD22)
    (get(RD35) == 'Broadly used, across teams')
    (get('RD01') == True) and not get('RD02')

This file reads that text into a small tree (read_trigger), works out whether it is true for one team's answers
(evaluate), and writes it back in one tidy form (to_text). It never runs the text as code: there is no eval, exec or
ast here. Three steps, each a short function:

    1. split_into_tokens   the text becomes pieces: numbers, quoted text, names, operators, brackets
    2. Parser              the pieces become a tree, following the grammar below
    3. evaluate            the tree is walked, and gives True or False

The grammar, lowest binding first:

    or-expression   and-expression ( ("or" | "||") and-expression )*
    and-expression  not-expression ( ("and" | "&&") not-expression )*
    not-expression  ("not" | "!") not-expression | comparison
    comparison      value ( ("==" | "!=" | ">=" | "<=" | ">" | "<") value )?
    value           a number | quoted text | True | False | None | a function call | ( or-expression )
    function call   name ( value, value, ... )        get, prevailing, to_int, to_float

The tree is made of plain tuples; the first item says what it is:

    ("number", 3.0)   ("text", "Broadly used")   ("yes_no", True)   ("none",)
    ("call", "get", [argument, ...])              a bare code inside get(...) is ("text", "RD22")
    ("not", x)   ("and", a, b)   ("or", a, b)   ("compare", sign, a, b)
"""
import math
import re

LONGEST_TRIGGER = 2000                                   # characters; a real trigger is about 20 to 80

# Kinds of piece (token).
NUMBER, TEXT, NAME, SIGN, WORD_OPERATOR, OPEN, CLOSE, COMMA = "number", "text", "name", "sign", "operator", "(", ")", ","

SIGNS = ("==", "!=", ">=", "<=", ">", "<")               # two-character signs first, so ">=" is not read as ">"
AND_WORDS, OR_WORDS, NOT_WORDS = ("and", "&&"), ("or", "||"), ("not", "!")
LITERAL_WORDS = {"true": ("yes_no", True), "false": ("yes_no", False), "none": ("none",)}

# The functions, and how many values each takes.
FUNCTIONS = {"get": 1, "prevailing": 1, "to_int": 1, "to_float": 1}
CODE_FUNCTIONS = ("get", "prevailing")                   # these take an answer's code, quoted or not

NUMBER_AT_START = re.compile(r"-?(?:\d+(?:\.\d*)?|\.\d+)")
NAME_AT_START = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

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
# Step 1: pieces
# ---------------------------------------------------------------------------------------------------

def split_into_tokens(text):
    """The trigger as a list of (kind, value, position). Spaces are skipped."""
    if len(text) > LONGEST_TRIGGER:
        raise TriggerProblem(f"The trigger is longer than {LONGEST_TRIGGER} characters, so it was not read.")
    tokens = []
    position = 0
    while position < len(text):
        character = text[position]
        rest = text[position:]
        if character.isspace():
            position += 1
            continue
        if character in "'\"":
            value, position_after = read_quoted_text(text, position)
            tokens.append((TEXT, value, position))
            position = position_after
            continue
        number_found = NUMBER_AT_START.match(rest)
        if number_found:
            tokens.append((NUMBER, float(number_found.group()), position))
            position += number_found.end()
            continue
        sign_found = next((sign for sign in SIGNS if rest.startswith(sign)), None)
        if sign_found:
            tokens.append((SIGN, sign_found, position))
            position += len(sign_found)
            continue
        two_characters = rest[:2]
        if two_characters in ("&&", "||"):
            tokens.append((WORD_OPERATOR, two_characters, position))
            position += 2
            continue
        if character == "!":
            tokens.append((WORD_OPERATOR, "!", position))
            position += 1
            continue
        if character in "(),":
            tokens.append((character, character, position))
            position += 1
            continue
        name_found = NAME_AT_START.match(rest)
        if name_found:
            word = name_found.group()
            kind = WORD_OPERATOR if word.lower() in ("and", "or", "not") else NAME
            tokens.append((kind, word.lower() if kind == WORD_OPERATOR else word, position))
            position += name_found.end()
            continue
        if character == "=":
            raise problem_at(position, character, "use == to compare two things (a single = is not used).")
        raise problem_at(position, character, "this character is not part of the trigger language.")
    return tokens


def read_quoted_text(text, start):
    """The text between quotes, and where the closing quote ends. Either kind of quote works; the other kind, commas
    and spaces inside are just text. A backslash puts the next character in as it is (\\' for a quote)."""
    quote = text[start]
    pieces = []
    position = start + 1
    while position < len(text):
        character = text[position]
        if character == "\\" and position + 1 < len(text):
            pieces.append(text[position + 1])
            position += 2
            continue
        if character == quote:
            return "".join(pieces), position + 1
        pieces.append(character)
        position += 1
    raise problem_at(start, text[start:start + 12], "the quote is never closed.")


# ---------------------------------------------------------------------------------------------------
# Step 2: the tree
# ---------------------------------------------------------------------------------------------------

class Parser:
    """Follows the grammar in the top note, one method for each line of it."""

    def __init__(self, text, tokens):
        self.text = text
        self.tokens = tokens
        self.next_index = 0

    # -- moving along the pieces
    def peek(self):
        return self.tokens[self.next_index] if self.next_index < len(self.tokens) else None

    def take(self):
        token = self.peek()
        self.next_index += 1
        return token

    def next_is_operator(self, words):
        token = self.peek()
        return token is not None and token[0] == WORD_OPERATOR and token[1] in words

    def refuse(self, token, reason):
        if token is None:
            raise problem_at(len(self.text), None, reason)
        raise problem_at(token[2], self.text[token[2]:token[2] + 12].strip() or token[1], reason)

    def expect(self, kind, reason):
        token = self.peek()
        if token is None or token[0] != kind:
            self.refuse(token, reason)
        return self.take()

    # -- the grammar
    def read_all(self):
        tree = self.or_expression()
        leftover = self.peek()
        if leftover is not None:
            self.refuse(leftover, "this does not fit after what came before it. Join two tests with and, or.")
        return tree

    def or_expression(self):
        tree = self.and_expression()
        while self.next_is_operator(OR_WORDS):
            self.take()
            tree = ("or", tree, self.and_expression())
        return tree

    def and_expression(self):
        tree = self.not_expression()
        while self.next_is_operator(AND_WORDS):
            self.take()
            tree = ("and", tree, self.not_expression())
        return tree

    def not_expression(self):
        if self.next_is_operator(NOT_WORDS):
            self.take()
            return ("not", self.not_expression())
        return self.comparison()

    def comparison(self):
        left = self.value()
        token = self.peek()
        if token is not None and token[0] == SIGN:
            self.take()
            right = self.value()
            after = self.peek()
            if after is not None and after[0] == SIGN:
                self.refuse(after, "only one comparison at a time. Join two comparisons with and, or.")
            return ("compare", token[1], left, right)
        return left

    def value(self):
        token = self.take()
        if token is None:
            self.refuse(None, "the trigger stops where a value was expected.")
        kind, content, _position = token
        if kind == NUMBER:
            return ("number", content)
        if kind == TEXT:
            return ("text", content)
        if kind == OPEN:
            tree = self.or_expression()
            self.expect(CLOSE, "a bracket was opened and not closed. Add a closing bracket.")
            return tree
        if kind == NAME:
            return self.name_or_call(token)
        self.refuse(token, "a value was expected here (a number, quoted text, True, False or get('RD01')).")

    def name_or_call(self, token):
        _kind, word, _position = token
        following = self.peek()
        is_call = following is not None and following[0] == OPEN
        if not is_call:
            if word.lower() in LITERAL_WORDS:
                return LITERAL_WORDS[word.lower()]
            self.refuse(token, "text must be in quotes, for example 'Broadly used'. A code is only written inside get(...) or prevailing(...).")
        if word.lower() not in FUNCTIONS:
            names = ", ".join(sorted(FUNCTIONS))
            self.refuse(token, f"'{word}' is not a function this language has. The functions are {names}.")
        function = word.lower()
        self.take()                                       # the opening bracket
        arguments = [self.argument(function)]
        while self.peek() is not None and self.peek()[0] == COMMA:
            self.take()
            arguments.append(self.argument(function))
        closing = self.peek()
        if len(arguments) != FUNCTIONS[function]:
            self.refuse(closing or token, f"{function}(...) takes {FUNCTIONS[function]} value, and was given {len(arguments)}.")
        self.expect(CLOSE, f"{function}( is not closed. Add a closing bracket.")
        return ("call", function, arguments)

    def argument(self, function):
        """One value inside a function's brackets. get and prevailing may be given the code unquoted: get(RD22)."""
        token = self.peek()
        following = self.tokens[self.next_index + 1] if self.next_index + 1 < len(self.tokens) else None
        bare_code = (token is not None and token[0] == NAME and function in CODE_FUNCTIONS
                     and (following is None or following[0] != OPEN))
        if bare_code:
            self.take()
            return ("text", token[1])
        argument = self.or_expression()
        if function in CODE_FUNCTIONS and argument[0] != "text":
            self.refuse(token, f"{function}(...) needs a code such as RD01, with or without quotes.")
        return argument


def read_trigger(text):
    """The trigger as a tree. Raises TriggerProblem (a ValueError) with a plain sentence when it can't be read, or
    when it looks at no answer at all."""
    shown = "" if text is None else str(text)
    if not shown.strip():
        raise TriggerProblem("The trigger is empty.")
    tree = Parser(shown, split_into_tokens(shown)).read_all()
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
    if kind == "not":
        return [tree[1]]
    if kind in ("and", "or"):
        return [tree[1], tree[2]]
    if kind == "compare":
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
    """What each answer is compared with: {code: {"text": [choices], "yes_no": True or False, "number": True or False}}.
    The form uses this to choose the kind of question: a field compared with text gets those texts as its choices."""
    uses = {code: {"text": [], "yes_no": False, "number": False} for code in fields_in_order(tree)}
    _note_uses(tree, uses)
    return uses


def _answer_looked_at(side):
    """(code, wrapped_in_a_number_function) when this side of a comparison is get(code) or to_int(get(code)); else None."""
    if side[0] == "call" and side[1] == "get":
        return side[2][0][1], False
    if side[0] == "call" and side[1] in ("to_int", "to_float"):
        inner = _answer_looked_at(side[2][0])
        return (inner[0], True) if inner else None
    return None


def _note_uses(tree, uses):
    if tree[0] == "compare":
        _sign, left, right = tree[1], tree[2], tree[3]
        for side, other in ((left, right), (right, left)):
            looked_at = _answer_looked_at(side)
            if looked_at is None:
                continue
            code, as_number = looked_at
            if as_number or other[0] == "number" or (other[0] == "call" and other[1] in ("prevailing", "to_int", "to_float")):
                uses[code]["number"] = True
            elif other[0] == "text" and other[1] not in uses[code]["text"]:
                uses[code]["text"].append(other[1])
            elif other[0] == "yes_no":
                uses[code]["yes_no"] = True
        return
    if tree[0] == "call" and tree[1] == "get":
        uses[tree[2][0][1]]["yes_no"] = True              # get(code) on its own is a yes or no
        return
    for child in children_of(tree):
        _note_uses(child, uses)


# ---------------------------------------------------------------------------------------------------
# Step 3: working out true or false
# ---------------------------------------------------------------------------------------------------

def is_missing(value):
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
    yes_no = as_yes_no(value)
    if yes_no is not None:
        return yes_no
    number = as_number(value)
    return number != 0 if number is not None else False


def compare(sign, left, right):
    """One comparison. Comparing with a missing answer is False (never an error), except None == None."""
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

    answer_of(code)      the team's answer: True or False for a yes or no, a number, text, or None when missing
    prevailing_of(code)  the prevailing median for a data field, or None
    """
    value = _value_of(tree, answer_of, prevailing_of or (lambda code: None))
    return as_truth(value)


def _value_of(tree, answer_of, prevailing_of):
    kind = tree[0]
    if kind == "number":
        return tree[1]
    if kind == "text":
        return tree[1]
    if kind == "yes_no":
        return tree[1]
    if kind == "none":
        return None
    if kind == "not":
        return not as_truth(_value_of(tree[1], answer_of, prevailing_of))
    if kind == "and":
        return as_truth(_value_of(tree[1], answer_of, prevailing_of)) and as_truth(_value_of(tree[2], answer_of, prevailing_of))
    if kind == "or":
        return as_truth(_value_of(tree[1], answer_of, prevailing_of)) or as_truth(_value_of(tree[2], answer_of, prevailing_of))
    if kind == "compare":
        return compare(tree[1], _value_of(tree[2], answer_of, prevailing_of), _value_of(tree[3], answer_of, prevailing_of))
    return _call_value(tree, answer_of, prevailing_of)


def _call_value(tree, answer_of, prevailing_of):
    function, arguments = tree[1], tree[2]
    if function == "get":
        answer = answer_of(arguments[0][1])
        return None if is_missing(answer) else answer
    if function == "prevailing":
        return as_number(prevailing_of(arguments[0][1]))
    inside = _value_of(arguments[0], answer_of, prevailing_of)
    return to_int(inside) if function == "to_int" else to_float(inside)


def evaluate_or_unknown(tree, answer_of, prevailing_of=None):
    """True or False, or None when it can't be told: every answer the trigger asks for is missing, or a prevailing
    median it needs isn't there. A driver that can't be told is never counted as on."""
    prevailing_of = prevailing_of or (lambda code: None)
    asked_for = fields_used(tree)
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


def _written(tree, inside_a_join):
    kind = tree[0]
    if kind == "number":
        number = tree[1]
        return str(int(number)) if number == int(number) else repr(number)
    if kind == "text":
        escaped = tree[1].replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if kind == "yes_no":
        return "True" if tree[1] else "False"
    if kind == "none":
        return "None"
    if kind == "call":
        return f"{tree[1]}({', '.join(_written(argument, False) for argument in tree[2])})"
    if kind == "compare":
        return f"({_written(tree[2], False)} {tree[1]} {_written(tree[3], False)})"
    if kind == "not":
        inner = _written(tree[1], True)
        return f"not {inner}"
    joiner = f" {kind} "
    joined = _written(tree[1], True) + joiner + _written(tree[2], True)
    return f"({joined})" if inside_a_join else joined
