from psycopg2.extensions import QuotedString
import enum

class Column(enum.Enum):
    ord = 1
    pattern = 2
    fts = 3

class Op(enum.Enum):
    eq = 1
    ge = 2
    gt = 3
    le = 4
    lt = 5
    
    def to_sql(self):
        if self == Op.eq:
            return "="
        elif self == Op.ge:
            return ">="
        elif self == Op.gt:
            return ">"
        elif self == Op.le:
            return "<="
        elif self == Op.lt:
            return "<"
        else:
            raise NotImplementedError

class ParserException(Exception):
    pass

class SyntaxException(Exception):
    pass

def quote(string):
    return QuotedString(string).getquoted().decode("utf-8")

class Atom:
    TAG_TO_COLUMN = {
        "id": ("qid", Column.ord),
        "quote": ("quote", Column.fts),
        "name": ("attrib_name", Column.pattern),
        "date": ("attrib_date", Column.ord),
    }
    
    FTS_TAGS = {
        tag
        for tag, (column, type) in TAG_TO_COLUMN.items()
        if type == Column.fts
    }

    def __init__(self, tag, op, raw_value, value=None):
        self.tag = tag
        self.op = op
        self.value = quote(raw_value) if value is None else value
        self.raw_value = raw_value
        
        if self.tag not in self.TAG_TO_COLUMN:
            raise ParserException("Unrecognised tag %r" % self.tag)
        if self.TAG_TO_COLUMN[self.tag][1] != Column.ord and self.op != Op.eq:
            self.op = Op.eq

    def to_sql(self):
        column, type = self.TAG_TO_COLUMN[self.tag]
        if type == Column.ord:
            return "%s %s %s" % (column, self.op.to_sql(), self.value)
        elif type == Column.pattern:
            value = "%" + self.raw_value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            return "%s ILIKE %s" % (column, quote(value))
        elif type == Column.fts:
            return "TO_TSVECTOR('english', %s) @@ TO_TSQUERY('english', %s)" % (column, quote(self.value))
        else:
            raise NotImplementedError

class NotDeleted:
    def to_sql(self):
        return "NOT deleted"

class And:
    def __init__(self, nodes):
        self.nodes = nodes
    
    def to_sql(self):
        return "(" + " AND ".join((n.to_sql() for n in self.nodes)) + ")"
    
class Or:
    def __init__(self, nodes):
        self.nodes = nodes
    
    def to_sql(self):
        return "(" + " OR ".join((n.to_sql() for n in self.nodes)) + ")"

class Parser:
    OPERATOR = {And: " & ", Or: " | "}

    def __init__(self, input):
        self.input = input
        self.offset = 0

    def parse(self):
        try:
            ast = self.parse_disjunction()
            self.eat_whitespace()
            if self.offset != len(self.input):
                # Interpret garbage at the end of the input as yet another quote tag.
                return self.optimise(And([ast, Atom("quote", Op.eq, self.input[self.offset:]), NotDeleted()]))
            return self.optimise(And([ast, NotDeleted()]))
        except (SyntaxException, RecursionError):
            return Atom("quote", Op.eq, self.input)
    
    def optimise(self, ast):
        ast = self.optimise_and_or_collapse_pass(ast)
        ast = self.optimise_fts_merge_pass(ast)
        return ast
    
    def optimise_and_or_collapse_pass(self, ast):
        # ('is' & ('bear' & ('go' & ('to' & 'moon?')))) => 'is' & 'bear' & 'go' & 'to' & 'moon?'
        # ('is' | ('bear' | ('go' | ('to' | 'moon?')))) => 'is' | 'bear' | 'go' | 'to' | 'moon?'
        if isinstance(ast, (And, Or)):
            nodes = []
            expanded = False
            for node in ast.nodes:
                if type(node) == type(ast):
                    nodes.extend(map(self.optimise_and_or_collapse_pass, node.nodes))
                    expanded = True
                else:
                    nodes.append(self.optimise_and_or_collapse_pass(node))
            ast = type(ast)(nodes)
            if expanded:
                return self.optimise_and_or_collapse_pass(ast)
        return ast

    def optimise_fts_merge_pass(self, ast):
        # 'is' & 'bear' & 'go' & 'to' & 'moon?' == "'is' & 'bear' & 'go' & 'to' & 'moon?'"
        # Important because when stop words like 'is' and 'to' get removed those queries will match nothing.
        # 'is' | 'bear' | 'go' | 'to' | 'moon?' == "'is' | 'bear' | 'go' | 'to' | 'moon?'"
        if isinstance(ast, (And, Or)):
            ast = type(ast)([self.optimise_fts_merge_pass(node) for node in ast.nodes])
            for tag in Atom.FTS_TAGS:
                value = self.OPERATOR[type(ast)].join((atom.value for atom in ast.nodes if isinstance(atom, Atom) and atom.tag == tag))
                nodes = [node for node in ast.nodes if not isinstance(node, Atom) or node.tag != tag]
                if len(value) > 0:
                    nodes.append(Atom(tag, Op.eq, None, "(" + value + ")"))
                if len(nodes) == 1:
                    return nodes[0]
                else:
                    ast = type(ast)(nodes)
        return ast

    def expect(self, c):
        if self.offset == len(self.input):
            raise SyntaxException("%d: expected %r, found end of input" % (self.offset, c))
        if self.input[self.offset] != c:
            raise SyntaxException("%d: expected %r, found %r" % (self.offset, c, self.input[self.offset]))
        self.offset += 1
    
    def eat_whitespace(self):
        while self.offset < len(self.input) and self.input[self.offset].isspace():
            self.offset += 1
    
    def parse_token(self):
        self.eat_whitespace()
        
        start = self.offset
        end = self.offset
        while end < len(self.input) and not self.input[end].isspace() and self.input[end] not in {"(", ")", "|", "=", ">", "<", ":"}:
            end += 1
        
        if start != end:
            self.offset = end
            return self.input[start:end]
        raise SyntaxException("%d: expected a token" % self.offset)

    def parse_quoted_string(self):
        self.eat_whitespace()
        
        self.expect('"')
        start = self.offset
        while self.offset < len(self.input) and not self.input[self.offset] == '"':
            self.offset += 1
        self.expect('"')
        return self.input[start:self.offset-1]
    
    def parse_op(self):
        self.eat_whitespace()

        try:
            self.expect(":")
            return Op.eq
        except SyntaxException:
            pass

        try:
            self.expect("=")
            return Op.eq
        except SyntaxException:
            pass
        
        try:
            self.expect(">")
            try:
                self.expect("=")
                return Op.ge
            except SyntaxException:
                return Op.gt
        except SyntaxException:
            pass
        
        try:
            self.expect("<")
            try:
                self.expect("=")
                return Op.le
            except SyntaxException:
                return Op.lt
        except SyntaxException:
            raise SyntaxException("%d: expected ':', '<', '<=', '=', '=>', or '>'" % self.offset)
    
    def parse_atom(self):
        self.eat_whitespace()
        
        offset = self.offset
        try:
            return Atom("quote", Op.eq, self.parse_quoted_string())
        except SyntaxException:
            self.offset = offset
        
        tag = self.parse_token()
        offset = self.offset
        try:
            op = self.parse_op()
            
            value_offset = self.offset
            try:
                value = self.parse_quoted_string()
            except SyntaxException:
                self.offset = value_offset
            value = self.parse_token()
            try:
                return Atom(tag, op, value)
            except ParserException:
                return And([Atom("quote", Op.eq, tag), Atom("quote", Op.eq, value)])

            return Atom(tag, op, self.parse_token())
        except SyntaxException as e:
            self.offset = offset
        
        return Atom("quote", Op.eq, tag)

    def parse_expr(self):
        self.eat_whitespace()
        offset = self.offset
        try:
            self.expect('(')
            expr = self.parse_disjunction()
            self.expect(')')
            return expr
        except SyntaxException:
            self.offset = offset
        
        return self.parse_atom()

    def parse_conjunction(self):
        expr = self.parse_expr()
        offset = self.offset
        try:
            return And([expr, self.parse_conjunction()])
        except SyntaxException as e:
            self.offset = offset
        return expr
    
    def parse_disjunction(self):
        expr = self.parse_conjunction()
        self.eat_whitespace()
        offset = self.offset
        try:
            self.expect("|")
            return Or([expr, self.parse_disjunction()])
        except SyntaxException:
            self.offset = offset
        return expr
