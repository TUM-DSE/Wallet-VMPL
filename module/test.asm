BITS 64
section .text
_start:
    mov rax,0xa
_prep:
    mov rdx,100
_loop:
    push rax
    inc rax
    dec rdx
    jnz _loop
    mov rdx,100
_clean_loop:
    pop rcx
    dec rdx
    jnz _clean_loop
    jmp _prep
