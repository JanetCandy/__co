// This file is part of www.nand2tetris.org
// and the book "The Elements of Computing Systems"
// by Nisan and Schocken, MIT Press.
// File name: projects/04/Fill.asm

// Runs an infinite loop that listens to the keyboard input.
// When a key is pressed (any key), the program blackens the screen,
// i.e. writes "black" in every pixel;
// the screen should remain fully black as long as the key is pressed. 
// When no key is pressed, the program clears the screen, i.e. writes
// "white" in every pixel;
// the screen should remain fully clear as long as no key is pressed.

(CHECK_KBD)
    // 1. 預設顏色為白色 (0)
    @color
    M=0

    // 2. 讀取鍵盤狀態 (KBD 位址為 24576)
    @KBD
    D=M
    @DRAW_SETUP
    D;JEQ       // 若無按鍵 (KBD == 0)，維持白色並準備繪製

    // 3. 若有按鍵按下，將顏色設為黑色 (-1 / 0xFFFF)
    @color
    M=-1

(DRAW_SETUP)
    // 4. 初始化記憶體指標 address = SCREEN (20480)
    @SCREEN
    D=A
    @address
    M=D

(DRAW_LOOP)
    // 5. 檢查指標是否已到達螢幕末端 (20480 + 8192 = 24576，即 KBD 位址)
    @address
    D=M
    @KBD
    D=D-A
    @CHECK_KBD
    D;JEQ       // 若 address == KBD，代表整頁繪製完畢，跳回重新監聽鍵盤

    // 6. 將當前顏色寫入 address 指向的螢幕記憶體區塊
    @color
    D=M
    @address
    A=M
    M=D

    // 7. 指標移至下一個 16-bit 區塊並繼續迴圈
    @address
    M=M+1

    @DRAW_LOOP
    0;JMP