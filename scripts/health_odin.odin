package main

import "core:net"
import "core:strings"

main :: proc() {
	ep, ok := net.parse_endpoint("0.0.0.0:8082")
	if !ok {
		return
	}

	listener, err := net.listen_tcp(ep)
	if err != nil {
		return
	}
	defer net.close(listener)

	for {
		client, _, aerr := net.accept_tcp(listener)
		if aerr != nil {
			continue
		}
		handle_client(client)
	}
}

handle_client :: proc(client: net.TCP_Socket) {
	defer net.close(client)

	buf := make([]byte, 4096)
	n, rerr := net.recv_tcp(client, buf)
	if rerr != nil || n <= 0 {
		return
	}

	req := string(buf[:n])
	path := parse_path(req)
	if path == "/health" {
		response := "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nok"
		net.send_tcp(client, transmute([]byte)response)
	} else {
		response := "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nContent-Length: 9\r\n\r\nnot found"
		net.send_tcp(client, transmute([]byte)response)
	}
}

parse_path :: proc(req: string) -> string {
	first_space := strings.index(req, " ")
	if first_space < 0 {
		return ""
	}
	rest := req[first_space+1:]
	second_space := strings.index(rest, " ")
	if second_space < 0 {
		return ""
	}
	return rest[:second_space]
}
