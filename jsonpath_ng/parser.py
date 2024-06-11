import logging
import sys
import os.path

from typing import Iterator, List, Optional, Tuple

from ply.lex import LexToken
from ply.yacc import YaccProduction
import ply.yacc

from jsonpath_ng.exceptions import JsonPathParserError
from jsonpath_ng.jsonpath import *
from jsonpath_ng.lexer import JsonPathLexer

logger = logging.getLogger(__name__)


def parse(string: str):
    return JsonPathParser().parse(string)


class JsonPathParser:
    '''
    An LALR-parser for JsonPath
    '''

    tokens = JsonPathLexer.tokens

    def __init__(self, debug=False, lexer_class=None):
        if self.__doc__ is None:
            raise JsonPathParserError(
                'Docstrings have been removed! By design of PLY, '
                'jsonpath-rw requires docstrings. You must not use '
                'PYTHONOPTIMIZE=2 or python -OO.'
            )

        self.debug = debug
        self.lexer_class = lexer_class or JsonPathLexer # Crufty but works around statefulness in PLY

        # Since PLY has some crufty aspects and dumps files, we try to keep them local
        # However, we need to derive the name of the output Python file :-/
        output_directory = os.path.dirname(__file__)
        try:
            module_name = os.path.splitext(os.path.split(__file__)[1])[0]
        except:
            module_name = __name__

        start_symbol = 'jsonpath'
        parsing_table_module = '_'.join([module_name, start_symbol, 'parsetab'])

        # Generate the parse table
        self.parser = ply.yacc.yacc(module=self,
                                    debug=self.debug,
                                    tabmodule = parsing_table_module,
                                    outputdir = output_directory,
                                    write_tables=0,
                                    start = start_symbol,
                                    errorlog = logger)

    def parse(self, string: str, lexer = None):
        lexer = lexer or self.lexer_class()
        return self.parse_token_stream(lexer.tokenize(string))

    def parse_token_stream(self, token_iterator: Iterator):
        return self.parser.parse(lexer = IteratorToTokenStream(token_iterator))

    # ===================== PLY Parser specification =====================

    precedence: List[Tuple[str, ...]] = [
        ('left', ','),
        ('left', 'DOUBLEDOT'),
        ('left', '.'),
        ('left', '|'),
        ('left', '&'),
        ('left', 'WHERE'),
    ]

    def p_error(self, t: Optional[LexToken]):
        if t is None:
            raise JsonPathParserError('Parse error near the end of string!')
        raise JsonPathParserError('Parse error at %s:%s near token %s (%s)'
                                  % (t.lineno, t.lexpos, t.value, t.type))

    def p_jsonpath_binop(self, p: YaccProduction):
        """jsonpath : jsonpath '.' jsonpath
                    | jsonpath DOUBLEDOT jsonpath
                    | jsonpath WHERE jsonpath
                    | jsonpath '|' jsonpath
                    | jsonpath '&' jsonpath"""
        op = p[2]

        if op == '.':
            p[0] = Child(p[1], p[3])
        elif op == '..':
            p[0] = Descendants(p[1], p[3])
        elif op == 'where':
            p[0] = Where(p[1], p[3])
        elif op == '|':
            p[0] = Union(p[1], p[3])
        elif op == '&':
            p[0] = Intersect(p[1], p[3])

    def p_jsonpath_fields(self, p: YaccProduction):
        "jsonpath : fields_or_any"
        p[0] = Fields(*p[1])

    def p_jsonpath_named_operator(self, p: YaccProduction):
        "jsonpath : NAMED_OPERATOR"
        if p[1] == 'this':
            p[0] = This()
        elif p[1] == 'parent':
            p[0] = Parent()
        else:
            raise JsonPathParserError('Unknown named operator `%s` at %s:%s'
                                      % (p[1], p.lineno(1), p.lexpos(1)))

    def p_jsonpath_root(self, p: YaccProduction):
        "jsonpath : '$'"
        p[0] = Root()

    def p_jsonpath_idx(self, p: YaccProduction):
        "jsonpath : '[' idx ']'"
        p[0] = p[2]

    def p_jsonpath_slice(self, p: YaccProduction):
        "jsonpath : '[' slice ']'"
        p[0] = p[2]

    def p_jsonpath_fieldbrackets(self, p: YaccProduction):
        "jsonpath : '[' fields ']'"
        p[0] = Fields(*p[2])

    def p_jsonpath_child_fieldbrackets(self, p: YaccProduction):
        "jsonpath : jsonpath '[' fields ']'"
        p[0] = Child(p[1], Fields(*p[3]))

    def p_jsonpath_child_idxbrackets(self, p: YaccProduction):
        "jsonpath : jsonpath '[' idx ']'"
        p[0] = Child(p[1], p[3])

    def p_jsonpath_child_slicebrackets(self, p: YaccProduction):
        "jsonpath : jsonpath '[' slice ']'"
        p[0] = Child(p[1], p[3])

    def p_jsonpath_parens(self, p: YaccProduction):
        "jsonpath : '(' jsonpath ')'"
        p[0] = p[2]

    # Because fields in brackets cannot be '*' - that is reserved for array indices
    def p_fields_or_any(self, p: YaccProduction):
        """fields_or_any : fields
                         | '*'    """
        if p[1] == '*':
            p[0] = ['*']
        else:
            p[0] = p[1]

    def p_fields_id(self, p: YaccProduction):
        "fields : ID"
        p[0] = [p[1]]

    def p_fields_comma(self, p: YaccProduction):
        "fields : fields ',' fields"
        p[0] = p[1] + p[3]

    def p_idx(self, p: YaccProduction):
        "idx : NUMBER"
        p[0] = Index(p[1])

    def p_slice_any(self, p: YaccProduction):
        "slice : '*'"
        p[0] = Slice()

    def p_slice(self, p: YaccProduction): # Currently does not support `step`
        """slice : maybe_int ':' maybe_int
                 | maybe_int ':' maybe_int ':' maybe_int """
        p[0] = Slice(*p[1::2])

    def p_maybe_int(self, p: YaccProduction):
        """maybe_int : NUMBER
                     | empty"""
        p[0] = p[1]

    def p_empty(self, p: YaccProduction):
        'empty :'
        p[0] = None

class IteratorToTokenStream:
    def __init__(self, iterator: Iterator):
        self.iterator = iterator

    def token(self):
        try:
            return next(self.iterator)
        except StopIteration:
            return None


if __name__ == '__main__':
    logging.basicConfig()
    parser = JsonPathParser(debug=True)
    print(parser.parse(sys.stdin.read()))
