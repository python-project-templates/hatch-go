package main

// #include <Python.h>
// #include <stdlib.h>
// extern char* GoHello();
// extern long GoAdd(long a, long b);
//
// static PyObject* py_hello(PyObject* self, PyObject* args) {
//     char* result = GoHello();
//     PyObject* obj = PyUnicode_FromString(result);
//     free(result);
//     return obj;
// }
//
// static PyObject* py_add(PyObject* self, PyObject* args) {
//     long a, b;
//     if (!PyArg_ParseTuple(args, "ll", &a, &b)) {
//         return NULL;
//     }
//     return PyLong_FromLong(GoAdd(a, b));
// }
//
// static PyMethodDef ProjectMethods[] = {
//     {"hello", py_hello, METH_NOARGS, "Return a greeting string from Go."},
//     {"add", py_add, METH_VARARGS, "Add two integers using Go."},
//     {NULL, NULL, 0, NULL}
// };
//
// static struct PyModuleDef projectmodule = {
//     PyModuleDef_HEAD_INIT,
//     "project",
//     "A test Python extension module built with Go and cgo.",
//     -1,
//     ProjectMethods
// };
//
// PyMODINIT_FUNC PyInit_project(void) {
//     return PyModule_Create(&projectmodule);
// }
import "C"

func main() {}
