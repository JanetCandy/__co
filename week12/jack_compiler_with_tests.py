from __future__ import annotations

import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


KEYWORDS = {
    "class",
    "constructor",
    "function",
    "method",
    "field",
    "static",
    "var",
    "int",
    "char",
    "boolean",
    "void",
    "true",
    "false",
    "null",
    "this",
    "let",
    "do",
    "if",
    "else",
    "while",
    "return",
}

SYMBOLS = set("{}()[].,;+-*/&|<>=~")

OP_TO_VM: Dict[str, str] = {
    "+": "add",
    "-": "sub",
    "*": "call Math.multiply 2",
    "/": "call Math.divide 2",
    "&": "and",
    "|": "or",
    "<": "lt",
    ">": "gt",
    "=": "eq",
}

UNARY_OP_TO_VM: Dict[str, str] = {
    "-": "neg",
    "~": "not",
}


@dataclass
class Token:
    kind: str  # keyword, symbol, integerConstant, stringConstant, identifier
    value: str


class JackTokenizer:
    """移除註解並將 Jack 原始碼切分為 Token 串流。"""

    TOKEN_RE = re.compile(
        r'"[^"\n]*"'
        r"|\d+"
        r"|[A-Za-z_][A-Za-z0-9_]*"
        r"|[{}()\[\].,;+\-*/&|<>=~]"
    )

    def __init__(self, source: str) -> None:
        cleaned = self._strip_comments(source)
        raw_tokens = self.TOKEN_RE.findall(cleaned)
        self.tokens: List[Token] = [self._classify(t) for t in raw_tokens]
        self.pos: int = 0

    @staticmethod
    def _strip_comments(code: str) -> str:
        no_block = re.sub(r"/\*[\s\S]*?\*/", " ", code)
        no_line = re.sub(r"//[^\n]*", " ", no_block)
        return no_line

    @staticmethod
    def _classify(raw: str) -> Token:
        if raw.startswith('"') and raw.endswith('"'):
            return Token("stringConstant", raw[1:-1])
        if raw.isdigit():
            return Token("integerConstant", raw)
        if raw in KEYWORDS:
            return Token("keyword", raw)
        if raw in SYMBOLS:
            return Token("symbol", raw)
        return Token("identifier", raw)

    def has_more_tokens(self) -> bool:
        return self.pos < len(self.tokens)

    def current(self) -> Optional[Token]:
        return self.tokens[self.pos] if self.has_more_tokens() else None

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok


@dataclass
class SymbolEntry:
    type_name: str
    kind: str  # static, field, arg, var
    index: int


class SymbolTable:
    """管理 Class 與 Subroutine 兩層符號表。"""

    def __init__(self) -> None:
        self.class_table: Dict[str, SymbolEntry] = {}
        self.subroutine_table: Dict[str, SymbolEntry] = {}
        self.counts: Dict[str, int] = {"static": 0, "field": 0, "arg": 0, "var": 0}

    def start_subroutine(self) -> None:
        self.subroutine_table.clear()
        self.counts["arg"] = 0
        self.counts["var"] = 0

    def define(self, name: str, type_name: str, kind: str) -> None:
        idx = self.counts[kind]
        entry = SymbolEntry(type_name=type_name, kind=kind, index=idx)
        self.counts[kind] += 1
        if kind in ("static", "field"):
            self.class_table[name] = entry
        elif kind in ("arg", "var"):
            self.subroutine_table[name] = entry
        else:
            raise ValueError(f"Unknown symbol kind: {kind}")

    def var_count(self, kind: str) -> int:
        return self.counts[kind]

    def find(self, name: str) -> Optional[SymbolEntry]:
        if name in self.subroutine_table:
            return self.subroutine_table[name]
        if name in self.class_table:
            return self.class_table[name]
        return None


class VMWriter:
    """輸出 Nand2Tetris VM 指令。"""

    SEGMENT_MAP = {
        "var": "local",
        "arg": "argument",
        "field": "this",
        "static": "static",
    }

    def __init__(self) -> None:
        self.lines: List[str] = []

    def write_push(self, segment: str, index: int) -> None:
        self.lines.append(f"push {segment} {index}")

    def write_pop(self, segment: str, index: int) -> None:
        self.lines.append(f"pop {segment} {index}")

    def write_arithmetic(self, command: str) -> None:
        self.lines.append(command)

    def write_label(self, label: str) -> None:
        self.lines.append(f"label {label}")

    def write_goto(self, label: str) -> None:
        self.lines.append(f"goto {label}")

    def write_if(self, label: str) -> None:
        self.lines.append(f"if-goto {label}")

    def write_call(self, name: str, n_args: int) -> None:
        self.lines.append(f"call {name} {n_args}")

    def write_function(self, name: str, n_locals: int) -> None:
        self.lines.append(f"function {name} {n_locals}")

    def write_return(self) -> None:
        self.lines.append("return")

    def to_vm_code(self) -> str:
        return "\n".join(self.lines) + ("\n" if self.lines else "")


class CompilationEngine:
    """遞迴下降編譯器，直接將 Jack 語法轉譯為 VM 指令。"""

    def __init__(self, tokenizer: JackTokenizer) -> None:
        self.tok = tokenizer
        self.symbols = SymbolTable()
        self.vm = VMWriter()
        self.class_name = ""
        self.label_counter = 0

    def _new_label(self, prefix: str) -> str:
        lbl = f"{prefix}{self.label_counter}"
        self.label_counter += 1
        return lbl

    def _expect(
        self,
        expected_value: Optional[str] = None,
        expected_kind: Optional[str] = None,
    ) -> Token:
        tok = self.tok.current()
        if tok is None:
            raise SyntaxError(f"Unexpected EOF while expecting {expected_value or expected_kind}")
        if expected_kind is not None and tok.kind != expected_kind:
            raise SyntaxError(f"Expected kind '{expected_kind}', got '{tok.value}' ({tok.kind})")
        if expected_value is not None and tok.value != expected_value:
            raise SyntaxError(f"Expected '{expected_value}', got '{tok.value}'")
        return self.tok.advance()

    def _expect_type(self) -> str:
        tok = self.tok.current()
        if tok is None:
            raise SyntaxError("Unexpected EOF while expecting type")
        if tok.kind == "keyword" and tok.value in ("int", "char", "boolean"):
            return self.tok.advance().value
        if tok.kind == "identifier":
            return self.tok.advance().value
        raise SyntaxError(f"Expected type, got '{tok.value}'")

    def compile_class(self) -> str:
        self._expect("class", "keyword")
        self.class_name = self._expect(expected_kind="identifier").value
        self._expect("{", "symbol")

        while self.tok.current() and self.tok.current().value in ("static", "field"):
            self.compile_class_var_dec()

        while self.tok.current() and self.tok.current().value in ("constructor", "function", "method"):
            self.compile_subroutine()

        self._expect("}", "symbol")
        return self.vm.to_vm_code()

    def compile_class_var_dec(self) -> None:
        kind = self._expect(expected_kind="keyword").value
        type_name = self._expect_type()
        first_name = self._expect(expected_kind="identifier").value
        self.symbols.define(first_name, type_name, kind)

        while self.tok.current() and self.tok.current().value == ",":
            self._expect(",", "symbol")
            var_name = self._expect(expected_kind="identifier").value
            self.symbols.define(var_name, type_name, kind)

        self._expect(";", "symbol")

    def compile_subroutine(self) -> None:
        sub_kind = self._expect(expected_kind="keyword").value
        ret_tok = self.tok.current()
        if ret_tok and ret_tok.kind in ("keyword", "identifier"):
            self.tok.advance()
        else:
            raise SyntaxError(f"Invalid return type: {ret_tok}")

        sub_name = self._expect(expected_kind="identifier").value
        self.symbols.start_subroutine()

        if sub_kind == "method":
            self.symbols.define("this", self.class_name, "arg")

        self._expect("(", "symbol")
        self.compile_parameter_list()
        self._expect(")", "symbol")

        self._expect("{", "symbol")
        while self.tok.current() and self.tok.current().value == "var":
            self.compile_var_dec()

        n_locals = self.symbols.var_count("var")
        self.vm.write_function(f"{self.class_name}.{sub_name}", n_locals)

        if sub_kind == "constructor":
            n_fields = self.symbols.var_count("field")
            self.vm.write_push("constant", n_fields)
            self.vm.write_call("Memory.alloc", 1)
            self.vm.write_pop("pointer", 0)
        elif sub_kind == "method":
            self.vm.write_push("argument", 0)
            self.vm.write_pop("pointer", 0)

        self.compile_statements()
        self._expect("}", "symbol")

    def compile_parameter_list(self) -> None:
        if self.tok.current() and self.tok.current().value != ")":
            param_type = self._expect_type()
            param_name = self._expect(expected_kind="identifier").value
            self.symbols.define(param_name, param_type, "arg")

            while self.tok.current() and self.tok.current().value == ",":
                self._expect(",", "symbol")
                p_type = self._expect_type()
                p_name = self._expect(expected_kind="identifier").value
                self.symbols.define(p_name, p_type, "arg")

    def compile_var_dec(self) -> None:
        self._expect("var", "keyword")
        var_type = self._expect_type()
        first_name = self._expect(expected_kind="identifier").value
        self.symbols.define(first_name, var_type, "var")

        while self.tok.current() and self.tok.current().value == ",":
            self._expect(",", "symbol")
            name = self._expect(expected_kind="identifier").value
            self.symbols.define(name, var_type, "var")

        self._expect(";", "symbol")

    def compile_statements(self) -> None:
        while self.tok.current() and self.tok.current().value in ("let", "if", "while", "do", "return"):
            kw = self.tok.current().value
            if kw == "let":
                self.compile_let()
            elif kw == "if":
                self.compile_if()
            elif kw == "while":
                self.compile_while()
            elif kw == "do":
                self.compile_do()
            elif kw == "return":
                self.compile_return()

    def compile_let(self) -> None:
        self._expect("let", "keyword")
        var_name = self._expect(expected_kind="identifier").value
        entry = self.symbols.find(var_name)
        if entry is None:
            raise NameError(f"Undeclared variable '{var_name}' in {self.class_name}")

        is_array = False
        if self.tok.current() and self.tok.current().value == "[":
            is_array = True
            self._expect("[", "symbol")
            self.vm.write_push(VMWriter.SEGMENT_MAP[entry.kind], entry.index)
            self.compile_expression()
            self._expect("]", "symbol")
            self.vm.write_arithmetic("add")

        self._expect("=", "symbol")
        self.compile_expression()
        self._expect(";", "symbol")

        if is_array:
            self.vm.write_pop("temp", 0)
            self.vm.write_pop("pointer", 1)
            self.vm.write_push("temp", 0)
            self.vm.write_pop("that", 0)
        else:
            self.vm.write_pop(VMWriter.SEGMENT_MAP[entry.kind], entry.index)

    def compile_if(self) -> None:
        self._expect("if", "keyword")
        true_lbl = self._new_label("IF_TRUE")
        false_lbl = self._new_label("IF_FALSE")
        end_lbl = self._new_label("IF_END")

        self._expect("(", "symbol")
        self.compile_expression()
        self._expect(")", "symbol")

        self.vm.write_if(true_lbl)
        self.vm.write_goto(false_lbl)
        self.vm.write_label(true_lbl)

        self._expect("{", "symbol")
        self.compile_statements()
        self._expect("}", "symbol")

        has_else = bool(self.tok.current() and self.tok.current().value == "else")
        if has_else:
            self.vm.write_goto(end_lbl)

        self.vm.write_label(false_lbl)
        if has_else:
            self._expect("else", "keyword")
            self._expect("{", "symbol")
            self.compile_statements()
            self._expect("}", "symbol")
            self.vm.write_label(end_lbl)

    def compile_while(self) -> None:
        self._expect("while", "keyword")
        exp_lbl = self._new_label("WHILE_EXP")
        end_lbl = self._new_label("WHILE_END")

        self.vm.write_label(exp_lbl)
        self._expect("(", "symbol")
        self.compile_expression()
        self._expect(")", "symbol")

        self.vm.write_arithmetic("not")
        self.vm.write_if(end_lbl)

        self._expect("{", "symbol")
        self.compile_statements()
        self._expect("}", "symbol")

        self.vm.write_goto(exp_lbl)
        self.vm.write_label(end_lbl)

    def compile_do(self) -> None:
        self._expect("do", "keyword")
        self._compile_subroutine_call_after_first_ident(self._expect(expected_kind="identifier").value)
        self._expect(";", "symbol")
        self.vm.write_pop("temp", 0)

    def compile_return(self) -> None:
        self._expect("return", "keyword")
        if self.tok.current() and self.tok.current().value != ";":
            self.compile_expression()
        else:
            self.vm.write_push("constant", 0)
        self._expect(";", "symbol")
        self.vm.write_return()

    def compile_expression(self) -> None:
        self.compile_term()
        while self.tok.current() and self.tok.current().value in OP_TO_VM:
            op = self.tok.advance().value
            self.compile_term()
            self.vm.write_arithmetic(OP_TO_VM[op])

    def compile_term(self) -> None:
        tok = self.tok.current()
        if tok is None:
            raise SyntaxError("Unexpected EOF in expression")

        if tok.kind == "integerConstant":
            self.tok.advance()
            self.vm.write_push("constant", int(tok.value))
            return

        if tok.kind == "stringConstant":
            self.tok.advance()
            s = tok.value
            self.vm.write_push("constant", len(s))
            self.vm.write_call("String.new", 1)
            for ch in s:
                self.vm.write_push("constant", ord(ch))
                self.vm.write_call("String.appendChar", 2)
            return

        if tok.kind == "keyword":
            kw = self.tok.advance().value
            if kw == "true":
                self.vm.write_push("constant", 0)
                self.vm.write_arithmetic("not")
            elif kw in ("false", "null"):
                self.vm.write_push("constant", 0)
            elif kw == "this":
                self.vm.write_push("pointer", 0)
            else:
                raise SyntaxError(f"Unexpected keyword in term: {kw}")
            return

        if tok.kind == "symbol" and tok.value == "(":
            self._expect("(", "symbol")
            self.compile_expression()
            self._expect(")", "symbol")
            return

        if tok.kind == "symbol" and tok.value in UNARY_OP_TO_VM:
            uop = self.tok.advance().value
            self.compile_term()
            self.vm.write_arithmetic(UNARY_OP_TO_VM[uop])
            return

        if tok.kind == "identifier":
            ident = self.tok.advance().value
            nxt = self.tok.current()

            if nxt and nxt.value == "[":
                entry = self.symbols.find(ident)
                if entry is None:
                    raise NameError(f"Undeclared array '{ident}' in {self.class_name}")
                self._expect("[", "symbol")
                self.vm.write_push(VMWriter.SEGMENT_MAP[entry.kind], entry.index)
                self.compile_expression()
                self._expect("]", "symbol")
                self.vm.write_arithmetic("add")
                self.vm.write_pop("pointer", 1)
                self.vm.write_push("that", 0)
                return

            if nxt and nxt.value in ("(", "."):
                self._compile_subroutine_call_after_first_ident(ident)
                return

            entry = self.symbols.find(ident)
            if entry is None:
                raise NameError(f"Undeclared identifier '{ident}' in {self.class_name}")
            self.vm.write_push(VMWriter.SEGMENT_MAP[entry.kind], entry.index)
            return

        raise SyntaxError(f"Unexpected token in term: {tok.value} ({tok.kind})")

    def _compile_subroutine_call_after_first_ident(self, first_ident: str) -> None:
        nxt = self.tok.current()
        n_args = 0

        if nxt and nxt.value == ".":
            self._expect(".", "symbol")
            sub_name = self._expect(expected_kind="identifier").value
            entry = self.symbols.find(first_ident)
            if entry is not None:
                self.vm.write_push(VMWriter.SEGMENT_MAP[entry.kind], entry.index)
                n_args += 1
                target_class = entry.type_name
            else:
                target_class = first_ident
            full_name = f"{target_class}.{sub_name}"
        else:
            self.vm.write_push("pointer", 0)
            n_args += 1
            full_name = f"{self.class_name}.{first_ident}"

        self._expect("(", "symbol")
        n_args += self.compile_expression_list()
        self._expect(")", "symbol")
        self.vm.write_call(full_name, n_args)

    def compile_expression_list(self) -> int:
        count = 0
        if self.tok.current() and self.tok.current().value != ")":
            self.compile_expression()
            count += 1
            while self.tok.current() and self.tok.current().value == ",":
                self._expect(",", "symbol")
                self.compile_expression()
                count += 1
        return count


def compile_source_to_vm(source: str) -> str:
    tokenizer = JackTokenizer(source)
    engine = CompilationEngine(tokenizer)
    return engine.compile_class()


def compile_file(jack_path: Path) -> Path:
    source = jack_path.read_text(encoding="utf-8")
    vm_code = compile_source_to_vm(source)
    vm_path = jack_path.with_suffix(".vm")
    vm_path.write_text(vm_code, encoding="utf-8")
    return vm_path


def compile_target(target_path: str) -> List[Path]:
    p = Path(target_path)
    if not p.exists():
        raise FileNotFoundError(f"Path not found: {target_path}")

    outputs: List[Path] = []
    if p.is_file():
        if p.suffix != ".jack":
            raise ValueError("Input file must have a .jack extension")
        outputs.append(compile_file(p))
    elif p.is_dir():
        jack_files = sorted(p.glob("*.jack"))
        if not jack_files:
            raise ValueError(f"No .jack files found in directory: {target_path}")
        for jf in jack_files:
            outputs.append(compile_file(jf))
    return outputs


PROJECTS: Dict[str, Dict[str, str]] = {
    "Seven": {
        "Main.jack": """
class Main {
   function void main() {
      do Output.printInt(1 + (2 * 3));
      return;
   }
}
"""
    },
    "ConvertToBin": {
        "Main.jack": """
class Main {
    function void main() {
        var int value;
        do Main.fillMemory(8001, 16, -1);
        let value = Memory.peek(8000);
        do Main.convert(value);
        return;
    }

    function void convert(int value) {
        var int mask, position;
        var boolean loop;

        let loop = true;
        while (loop) {
            let position = position + 1;
            let mask = Main.nextMask(mask);

            if (~(position > 16)) {
                if (~((value & mask) = 0)) {
                    do Memory.poke(8000 + position, 1);
                }
                else {
                    do Memory.poke(8000 + position, 0);
                }
            }
            else {
                let loop = false;
            }
        }
        return;
    }

    function int nextMask(int mask) {
        if (mask = 0) {
            return 1;
        }
        else {
            return mask * 2;
        }
    }

    function void fillMemory(int address, int length, int value) {
        while (length > 0) {
            do Memory.poke(address, value);
            let length = length - 1;
            let address = address + 1;
        }
        return;
    }
}
"""
    },
    "Average": {
        "Main.jack": """
class Main {
   function void main() {
      var Array a;
      var int length;
      var int i, sum;

      let length = Keyboard.readInt("How many numbers? ");
      let a = Array.new(length);

      let i = 0;
      while (i < length) {
         let a[i] = Keyboard.readInt("Enter a number: ");
         let sum = sum + a[i];
         let i = i + 1;
      }

      do Output.printString("The average is ");
      do Output.printInt(sum / length);
      return;
   }
}
"""
    },
    "ComplexArrays": {
        "Main.jack": """
class Main {
    function void main() {
        var Array a, b, c;

        let a = Array.new(10);
        let b = Array.new(5);
        let c = Array.new(1);

        let a[3] = 2;
        let a[4] = 8;
        let a[5] = 4;
        let b[a[3]] = a[3] + 3;
        let a[b[a[3]]] = a[a[5]] * b[((7 - a[3]) - Main.double(2)) + 1];
        let c[0] = null;
        let c = c[0];

        do Output.printString("Test 1: expected result: 5; actual result: ");
        do Output.printInt(b[2]);
        do Output.println();
        do Output.printString("Test 2: expected result: 40; actual result: ");
        do Output.printInt(a[5]);
        do Output.println();
        do Output.printString("Test 3: expected result: 0; actual result: ");
        do Output.printInt(c);
        do Output.println();

        let c = null;

        if (c = null) {
            do Main.fill(a, 10);
            let c = a[3];
            let c[1] = 33;
            let c = a[7];
            let c[1] = 77;
            let b = a[3];
            let b[1] = b[1] + c[1];
        }

        do Output.printString("Test 4: expected result: 77; actual result: ");
        do Output.printInt(c[1]);
        do Output.println();
        do Output.printString("Test 5: expected result: 110; actual result: ");
        do Output.printInt(b[1]);
        do Output.println();
        return;
    }

    function int double(int a) {
        return a * 2;
    }

    function void fill(Array a, int size) {
        while (size > 0) {
            let size = size - 1;
            let a[size] = Array.new(3);
        }
        return;
    }
}
"""
    },
    "Square": {
        "Main.jack": """
class Main {
    function void main() {
        var SquareGame game;
        let game = SquareGame.new();
        do game.run();
        do game.dispose();
        return;
    }
}
""",
        "Square.jack": """
class Square {
   field int x, y;
   field int size;

   constructor Square new(int ax, int ay, int asize) {
      let x = ax;
      let y = ay;
      let size = asize;
      do draw();
      return this;
   }

   method void dispose() {
      do Memory.deAlloc(this);
      return;
   }

   method void draw() {
      do Screen.setColor(true);
      do Screen.drawRectangle(x, y, x + size, y + size);
      return;
   }

   method void erase() {
      do Screen.setColor(false);
      do Screen.drawRectangle(x, y, x + size, y + size);
      return;
   }

   method void incSize() {
      if (((y + size) < 254) & ((x + size) < 510)) {
         do erase();
         let size = size + 2;
         do draw();
      }
      return;
   }

   method void decSize() {
      if (size > 2) {
         do erase();
         let size = size - 2;
         do draw();
      }
      return;
   }

   method void moveUp() {
      if (y > 1) {
         do Screen.setColor(false);
         do Screen.drawRectangle(x, (y + size) - 1, x + size, y + size);
         let y = y - 2;
         do Screen.setColor(true);
         do Screen.drawRectangle(x, y, x + size, y + 1);
      }
      return;
   }

   method void moveDown() {
      if ((y + size) < 254) {
         do Screen.setColor(false);
         do Screen.drawRectangle(x, y, x + size, y + 1);
         let y = y + 2;
         do Screen.setColor(true);
         do Screen.drawRectangle(x, (y + size) - 1, x + size, y + size);
      }
      return;
   }

   method void moveLeft() {
      if (x > 1) {
         do Screen.setColor(false);
         do Screen.drawRectangle((x + size) - 1, y, x + size, y + size);
         let x = x - 2;
         do Screen.setColor(true);
         do Screen.drawRectangle(x, y, x + 1, y + size);
      }
      return;
   }

   method void moveRight() {
      if ((x + size) < 510) {
         do Screen.setColor(false);
         do Screen.drawRectangle(x, y, x + 1, y + size);
         let x = x + 2;
         do Screen.setColor(true);
         do Screen.drawRectangle((x + size) - 1, y, x + size, y + size);
      }
      return;
   }
}
""",
        "SquareGame.jack": """
class SquareGame {
   field Square square;
   field int direction;

   constructor SquareGame new() {
      let square = Square.new(0, 0, 30);
      let direction = 0;
      return this;
   }

   method void dispose() {
      do square.dispose();
      do Memory.deAlloc(this);
      return;
   }

   method void moveSquare() {
      if (direction = 1) { do square.moveUp(); }
      if (direction = 2) { do square.moveDown(); }
      if (direction = 3) { do square.moveLeft(); }
      if (direction = 4) { do square.moveRight(); }
      do Sys.wait(5);
      return;
   }

   method void run() {
      var char key;
      var boolean exit;
      let exit = false;

      while (~exit) {
         while (key = 0) {
            let key = Keyboard.keyPressed();
            do moveSquare();
         }
         if (key = 81)  { let exit = true; }
         if (key = 90)  { do square.decSize(); }
         if (key = 88)  { do square.incSize(); }
         if (key = 131) { let direction = 1; }
         if (key = 133) { let direction = 2; }
         if (key = 130) { let direction = 3; }
         if (key = 132) { let direction = 4; }

         while (~(key = 0)) {
            let key = Keyboard.keyPressed();
            do moveSquare();
         }
      }
      return;
   }
}
""",
    },
    "Pong": {
        "Main.jack": """
class Main {
    function void main() {
        var PongGame game;
        do PongGame.newInstance();
        let game = PongGame.getInstance();
        do game.run();
        do game.dispose();
        return;
    }
}
""",
        "Bat.jack": """
class Bat {
    field int x, y;
    field int width, height;
    field int direction;

    constructor Bat new(int Ax, int Ay, int Awidth, int Aheight) {
        let x = Ax;
        let y = Ay;
        let width = Awidth;
        let height = Aheight;
        let direction = 2;
        do show();
        return this;
    }

    method void dispose() {
        do Memory.deAlloc(this);
        return;
    }

    method void show() {
        do Screen.setColor(true);
        do draw();
        return;
    }

    method void hide() {
        do Screen.setColor(false);
        do draw();
        return;
    }

    method void draw() {
        do Screen.drawRectangle(x, y, x + width, y + height);
        return;
    }

    method void setDirection(int Adirection) {
        let direction = Adirection;
        return;
    }

    method int getLeft() {
        return x;
    }

    method int getRight() {
        return x + width;
    }

    method void setWidth(int Awidth) {
        do hide();
        let width = Awidth;
        do show();
        return;
    }

    method void move() {
        if (direction = 1) {
            let x = x - 4;
            if (x < 0) { let x = 0; }
            do Screen.setColor(false);
            do Screen.drawRectangle((x + width) + 1, y, (x + width) + 4, y + height);
            do Screen.setColor(true);
            do Screen.drawRectangle(x, y, x + 3, y + height);
        }
        else {
            let x = x + 4;
            if ((x + width) > 511) { let x = 511 - width; }
            do Screen.setColor(false);
            do Screen.drawRectangle(x - 4, y, x - 1, y + height);
            do Screen.setColor(true);
            do Screen.drawRectangle((x + width) - 3, y, x + width, y + height);
        }
        return;
    }
}
""",
        "Ball.jack": """
class Ball {
    field int x, y;
    field int lengthx, lengthy;
    field int d, straightD, diagonalD;
    field boolean invert, positivex, positivey;
    field int leftWall, rightWall, topWall, bottomWall;
    field int wall;

    constructor Ball new(int Ax, int Ay,
                         int AleftWall, int ArightWall, int AtopWall, int AbottomWall) {
        let x = Ax;
        let y = Ay;
        let leftWall = AleftWall;
        let rightWall = ArightWall - 6;
        let topWall = AtopWall;
        let bottomWall = AbottomWall - 6;
        let wall = 0;
        do show();
        return this;
    }

    method void dispose() {
        do Memory.deAlloc(this);
        return;
    }

    method void show() {
        do Screen.setColor(true);
        do draw();
        return;
    }

    method void hide() {
        do Screen.setColor(false);
        do draw();
        return;
    }

    method void draw() {
        do Screen.drawRectangle(x, y, x + 5, y + 5);
        return;
    }

    method int getLeft() {
        return x;
    }

    method int getRight() {
        return x + 5;
    }

    method void setDestination(int destx, int desty) {
        var int dx, dy, temp;
        let lengthx = destx - x;
        let lengthy = desty - y;
        let dx = Math.abs(lengthx);
        let dy = Math.abs(lengthy);
        let invert = (dx < dy);

        if (invert) {
            let temp = dx;
            let dx = dy;
            let dy = temp;
            let positivex = (y < desty);
            let positivey = (x < destx);
        }
        else {
            let positivex = (x < destx);
            let positivey = (y < desty);
        }

        let d = (2 * dy) - dx;
        let straightD = 2 * dy;
        let diagonalD = 2 * (dy - dx);
        return;
    }

    method int move() {
        do hide();

        if (d < 0) { let d = d + straightD; }
        else {
            let d = d + diagonalD;

            if (positivey) {
                if (invert) { let x = x + 4; }
                else { let y = y + 4; }
            }
            else {
                if (invert) { let x = x - 4; }
                else { let y = y - 4; }
            }
        }

        if (positivex) {
            if (invert) { let y = y + 4; }
            else { let x = x + 4; }
        }
        else {
            if (invert) { let y = y - 4; }
            else { let x = x - 4; }
        }

        if (~(x > leftWall)) {
            let wall = 1;
            let x = leftWall;
        }
        if (~(x < rightWall)) {
            let wall = 2;
            let x = rightWall;
        }
        if (~(y > topWall)) {
            let wall = 3;
            let y = topWall;
        }
        if (~(y < bottomWall)) {
            let wall = 4;
            let y = bottomWall;
        }

        do show();
        return wall;
    }

    method void bounce(int bouncingDirection) {
        var int newx, newy, divLengthx, divLengthy, factor;

        let divLengthx = lengthx / 10;
        let divLengthy = lengthy / 10;
        if (bouncingDirection = 0) { let factor = 10; }
        else {
            if (((~(lengthx < 0)) & (bouncingDirection = 1)) | ((lengthx < 0) & (bouncingDirection = (-1)))) {
                let factor = 20;
            }
            else { let factor = 5; }
        }

        if (wall = 1) {
            let newx = 506;
            let newy = (divLengthy * (-50)) / divLengthx;
            let newy = y + (newy * factor);
        }
        else {
            if (wall = 2) {
                let newx = 0;
                let newy = (divLengthy * 50) / divLengthx;
                let newy = y + (newy * factor);
            }
            else {
                if (wall = 3) {
                    let newy = 250;
                    let newx = (divLengthx * (-25)) / divLengthy;
                    let newx = x + (newx * factor);
                }
                else {
                    let newy = 0;
                    let newx = (divLengthx * 25) / divLengthy;
                    let newx = x + (newx * factor);
                }
            }
        }

        do setDestination(newx, newy);
        return;
    }
}
""",
        "PongGame.jack": """
class PongGame {
    static PongGame instance;
    field Bat bat;
    field Ball ball;
    field int wall;
    field boolean exit;
    field int score;
    field int lastWall;
    field int batWidth;

    constructor PongGame new() {
        do Screen.clearScreen();
        let batWidth = 50;
        let bat = Bat.new(230, 229, batWidth, 7);
        let ball = Ball.new(253, 222, 0, 511, 0, 229);
        do ball.setDestination(400, 0);
        do Screen.drawRectangle(0, 238, 511, 240);
        do Output.moveCursor(22, 0);
        do Output.printString("Score: 0");

        let exit = false;
        let score = 0;
        let wall = 0;
        let lastWall = 0;
        return this;
    }

    method void dispose() {
        do bat.dispose();
        do ball.dispose();
        do Memory.deAlloc(this);
        return;
    }

    function void newInstance() {
        let instance = PongGame.new();
        return;
    }

    function PongGame getInstance() {
        return instance;
    }

    method void run() {
        var char key;

        while (~exit) {
            while ((key = 0) & (~exit)) {
                let key = Keyboard.keyPressed();
                do bat.move();
                do moveBall();
                do Sys.wait(50);
            }

            if (key = 130) { do bat.setDirection(1); }
            else {
                if (key = 132) { do bat.setDirection(2); }
                else {
                    if (key = 140) { let exit = true; }
                }
            }

            while ((~(key = 0)) & (~exit)) {
                let key = Keyboard.keyPressed();
                do bat.move();
                do moveBall();
                do Sys.wait(50);
            }
        }

        if (exit) {
            do Output.moveCursor(10, 27);
            do Output.printString("Game Over");
        }
        return;
    }

    method void moveBall() {
        var int bouncingDirection, batLeft, batRight, ballLeft, ballRight;

        let wall = ball.move();

        if ((wall > 0) & (~(wall = lastWall))) {
            let lastWall = wall;
            let bouncingDirection = 0;
            let batLeft = bat.getLeft();
            let batRight = bat.getRight();
            let ballLeft = ball.getLeft();
            let ballRight = ball.getRight();

            if (wall = 4) {
                let exit = (batLeft > ballRight) | (batRight < ballLeft);
                if (~exit) {
                    if (ballRight < (batLeft + 10)) { let bouncingDirection = -1; }
                    else {
                        if (ballLeft > (batRight - 10)) { let bouncingDirection = 1; }
                    }

                    let batWidth = batWidth - 2;
                    do bat.setWidth(batWidth);
                    let score = score + 1;
                    do Output.moveCursor(22, 7);
                    do Output.printInt(score);
                }
            }
            do ball.bounce(bouncingDirection);
        }
        return;
    }
}
""",
    },
}


def run_embedded_tests() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        for proj_name, files in PROJECTS.items():
            proj_dir = base / proj_name
            proj_dir.mkdir(parents=True, exist_ok=True)
            for fname, content in files.items():
                (proj_dir / fname).write_text(content, encoding="utf-8")

            vm_paths = compile_target(str(proj_dir))
            assert len(vm_paths) == len(files), f"{proj_name}: VM file count mismatch"
            all_vm = "\n".join(p.read_text(encoding="utf-8") for p in vm_paths)
            assert "function " in all_vm and "return" in all_vm, f"{proj_name}: invalid VM output"
            print(f"[PASS] {proj_name}: compiled {len(vm_paths)} file(s)")


def main() -> None:
    if len(sys.argv) == 1:
        run_embedded_tests()
        return

    if len(sys.argv) == 2 and sys.argv[1] == "--test":
        run_embedded_tests()
        return

    if len(sys.argv) == 2:
        generated = compile_target(sys.argv[1])
        for out in generated:
            print(f"Generated: {out}")
        return

    print("Usage: python jack_compiler_with_tests.py [--test | <file.jack | directory>]")
    sys.exit(1)


if __name__ == "__main__":
    main()