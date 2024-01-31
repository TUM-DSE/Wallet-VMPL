BITS 64
section .text
_start:
    mov rax, 0x1002000
    mov rdx, 0xFFFFFFFF
    mov [rax], rdx
    mov rax,0xa
    jmp _start
