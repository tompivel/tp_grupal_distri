package clientregistry

import (
	"net"
	"sync"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/messagehandler"
)

type ClientState struct {
	Conn    net.Conn
	Handler *messagehandler.MessageHandler
}

type ClientRegistry struct {
	mu      sync.Mutex
	clients []ClientState
}

func (r *ClientRegistry) Add(client ClientState) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.clients = append(r.clients, client)
}

func (r *ClientRegistry) Remove(index int) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if index >= 0 && index < len(r.clients) {
		r.clients = append(r.clients[:index], r.clients[index+1:]...)
	}
}

func (r *ClientRegistry) WithLock(fn func([]ClientState)) {
	r.mu.Lock()
	defer r.mu.Unlock()
	fn(r.clients)
}
