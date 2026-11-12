import sys
import os


class SymbolTable:
    """管理預定義符號、標籤 (Label) 與變數 (Variable) 的記憶體位址對應表"""

    def __init__(self):
        self.table = {
            "SP": 0, "LCL": 1, "ARG": 2, "THIS": 3, "THAT": 4,
            "R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5, "R6": 6, "R7": 7,
            "R8": 8, "R9": 9, "R10": 10, "R11": 11, "R12": 12, "R13": 13, "R14": 14, "R15": 15,
            "SCREEN": 16384, "KBD": 24576
        }
        self.next_var_address = 16  # 變數從 RAM[16] 開始動態分配

    def add_entry(self, symbol: str, address: int):
        self.table[symbol] = address

    def contains(self, symbol: str) -> bool:
        return symbol in self.table

    def get_address(self, symbol: str) -> int:
        return self.table[symbol]

    def add_variable(self, symbol: str) -> int:
        address = self.next_var_address
        self.table[symbol] = address
        self.next_var_address += 1
        return address


class Code:
    """將助記符 (Mnemonic) 翻譯為對應的二進位機器碼欄位"""

    DEST_MAP = {
        "": "000", "M": "001", "D": "010", "MD": "011",
        "A": "100", "AM": "101", "AD": "110", "AMD": "111"
    }

    COMP_MAP = {
        # a = 0
        "0": "0101010", "1": "0111111", "-1": "0111010",
        "D": "0001100", "A": "0110000", "!D": "0001101",
        "!A": "0110001", "-D": "0001111", "-A": "0110011",
        "D+1": "0011111", "A+1": "0110111", "D-1": "0001110",
        "A-1": "0110010", "D+A": "0000010", "D-A": "0010011",
        "A-D": "0000111", "D&A": "0000000", "D|A": "0010101",
        # a = 1
        "M": "1110000", "!M": "1110001", "-M": "1110011",
        "M+1": "1110111", "M-1": "1110010", "D+M": "1000010",
        "D-M": "1010011", "M-D": "1000111", "D&M": "1000000",
        "D|M": "1010101"
    }

    JUMP_MAP = {
        "": "000", "JGT": "001", "JEQ": "010", "JGE": "011",
        "JLT": "100", "JNE": "101", "JLE": "110", "JMP": "111"
    }

    @classmethod
    def dest(cls, mnemonic: str) -> str:
        return cls.DEST_MAP[mnemonic]

    @classmethod
    def comp(cls, mnemonic: str) -> str:
        return cls.COMP_MAP[mnemonic]

    @classmethod
    def jump(cls, mnemonic: str) -> str:
        return cls.JUMP_MAP[mnemonic]


class Parser:
    """讀取並過濾 .asm 檔案，拆解 A-Instruction、C-Instruction 與 L-Instruction"""

    A_COMMAND = "A_COMMAND"
    C_COMMAND = "C_COMMAND"
    L_COMMAND = "L_COMMAND"

    def __init__(self, filepath: str):
        self.commands = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                # 移除行內註解與所有空白字元
                clean_line = line.split("//")[0].strip().replace(" ", "")
                if clean_line:
                    self.commands.append(clean_line)
        self.current_idx = -1
        self.current_command = ""

    def has_more_commands(self) -> bool:
        return self.current_idx + 1 < len(self.commands)

    def advance(self):
        self.current_idx += 1
        self.current_command = self.commands[self.current_idx]

    def reset(self):
        self.current_idx = -1
        self.current_command = ""

    def command_type(self) -> str:
        if self.current_command.startswith("@"):
            return self.A_COMMAND
        elif self.current_command.startswith("(") and self.current_command.endswith(")"):
            return self.L_COMMAND
        else:
            return self.C_COMMAND

    def symbol(self) -> str:
        if self.command_type() == self.A_COMMAND:
            return self.current_command[1:]
        elif self.command_type() == self.L_COMMAND:
            return self.current_command[1:-1]
        raise ValueError("symbol() 僅適用於 A_COMMAND 或 L_COMMAND")

    def dest(self) -> str:
        if "=" in self.current_command:
            return self.current_command.split("=")[0]
        return ""

    def comp(self) -> str:
        cmd = self.current_command
        if "=" in cmd:
            cmd = cmd.split("=")[1]
        if ";" in cmd:
            cmd = cmd.split(";")[0]
        return cmd

    def jump(self) -> str:
        if ";" in self.current_command:
            return self.current_command.split(";")[1]
        return ""


def assemble(asm_path: str):
    if not asm_path.endswith(".asm"):
        raise ValueError("錯誤：輸入檔案必須為 .asm 格式")

    hack_path = asm_path[:-4] + ".hack"
    parser = Parser(asm_path)
    symbol_table = SymbolTable()

    # First Pass: 掃描所有標籤 (Label) 並記錄對應的 ROM 指令位址
    rom_address = 0
    while parser.has_more_commands():
        parser.advance()
        cmd_type = parser.command_type()
        if cmd_type == Parser.L_COMMAND:
            label = parser.symbol()
            symbol_table.add_entry(label, rom_address)
        else:
            rom_address += 1

    # Second Pass: 將所有指令翻譯為 16-bit 二進位機器碼
    parser.reset()
    machine_code = []

    while parser.has_more_commands():
        parser.advance()
        cmd_type = parser.command_type()

        if cmd_type == Parser.A_COMMAND:
            sym = parser.symbol()
            if sym.isdigit():
                address = int(sym)
            else:
                if symbol_table.contains(sym):
                    address = symbol_table.get_address(sym)
                else:
                    address = symbol_table.add_variable(sym)
            # 格式化為 16-bit (首位為 0 + 15-bit數值)
            binary_cmd = f"0{address:015b}"
            machine_code.append(binary_cmd)

        elif cmd_type == Parser.C_COMMAND:
            comp_bits = Code.comp(parser.comp())
            dest_bits = Code.dest(parser.dest())
            jump_bits = Code.jump(parser.jump())
            # C-Instruction 格式: 111 + comp + dest + jump
            binary_cmd = f"111{comp_bits}{dest_bits}{jump_bits}"
            machine_code.append(binary_cmd)

    with open(hack_path, "w", encoding="utf-8") as f:
        f.write("\n".join(machine_code) + "\n")

    print(f"組譯成功：{asm_path} -> {hack_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("使用方式: python assembler.py <檔案名稱.asm>")
        sys.exit(1)

    input_file = sys.argv[1]
    if not os.path.exists(input_file):
        print(f"錯誤：找不到檔案 '{input_file}'")
        sys.exit(1)

    assemble(input_file)