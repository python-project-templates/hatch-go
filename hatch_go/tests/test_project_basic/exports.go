package main

import "C"

//export GoHello
func GoHello() *C.char {
	return C.CString("A string from Go")
}

//export GoAdd
func GoAdd(a, b C.long) C.long {
	return a + b
}
