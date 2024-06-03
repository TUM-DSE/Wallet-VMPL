package main

import "net/http"
import "io"
import "fmt"
import "os"
import "unsafe"
import "reflect"
// #cgo LDFLAGS: -L. -lmonitorcall
// #include "monitor_call/request.h"
import "C"

//extern handle_request
func c_handle_request(z *byte, zs int32, t *byte, ts int32, d *byte, ds int32) int32
//extern request_init
func c_request_init() int32
//extern allocate_memory
func c_alloc(size int32) *byte
//extern free_memory
func c_free_memory(ptr *byte)

func handleRoot(w http.ResponseWriter, r *http.Request) {
	io.WriteString(w, "Test\n")
}

func handleRequest(w http.ResponseWriter, r *http.Request) {
	//ctx := r.Context()

	Zygote := r.URL.Query().Get("Zygote")
	Trustlet := r.URL.Query().Get("Trustlet")
	Input := r.URL.Query().Get("Input")

	//TODO: Load Zygote/Trustlet
	fmt.Printf("Zygote: %s\nTrustlet: %s\nInput: %s\n", Zygote, Trustlet, Input)
	
	z := getZygote()
	defer c_free_memory(z)
	t := getTrustlet()
	defer c_free_memory(t)
	d := getData()
	defer c_free_memory(d)

	fmt.Println(reflect.TypeOf(z))
    fmt.Println(reflect.TypeOf(t))
    fmt.Println(reflect.TypeOf(d))
	fmt.Println("Do Monitor Calls")
	c_handle_request(z,4,t,4,d,4)
}

func handleAttestation(w http.ResponseWriter, r *http.Request) {

}

func getZygote() *byte{

	fmt.Println("Catching Zygote")
	zp := c_alloc(4)
	z := unsafe.Slice((*byte)(zp),4)
	z[0] = 0
	z[1] = 1
	z[2] = 2
	z[3] = 3

	return zp
}

func getTrustlet() *byte{

	fmt.Println("Catching Trustlet")
	tp := c_alloc(4)
	t := unsafe.Slice((*byte)(tp),4)
	t[0] = 4
	t[1] = 5
	t[2] = 6
	t[3] = 7

	return tp
}

func getData() *byte{

	dp := c_alloc(4)
	d := unsafe.Slice((*byte)(dp),4)
	d[0] = 8
	d[1] = 9
	d[2] = 10
	d[3] = 11

	return dp
}

func serve() {

	mux := http.NewServeMux()
	mux.HandleFunc("/", handleRoot)
	mux.HandleFunc("/request", handleRequest)
	mux.HandleFunc("/attest", handleAttestation)

	_ = http.ListenAndServe(":8000", mux)
}

func main() {

	if c_request_init() == -1 {
		fmt.Println("Failed to access Monitor kernel driver")
		if false {
			os.Exit(-1)//For testing disabled
		}
	}
	serve()

}
