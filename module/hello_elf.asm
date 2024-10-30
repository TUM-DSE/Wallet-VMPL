global		_start
section 	.text
_start:
	push rbp
	mov rbp, rsp
	mov eax,0
loop:
	cpuid
	jmp loop
