// Package testmiddleware supplies a recording transport for worker tests.
package testmiddleware

import "github.com/7574-sistemas-distribuidos/tp-grupal-distri/sender-receiver-logic/middleware"

type Recorder struct {
	Messages []middleware.Message
	Err      error
}

func (r *Recorder) Send(m middleware.Message) error {
	if r.Err != nil {
		return r.Err
	}
	r.Messages = append(r.Messages, m)
	return nil
}
func (r *Recorder) SendToKey(m middleware.Message, _ string) error              { return r.Send(m) }
func (*Recorder) StartConsuming(func(middleware.Message, func(), func())) error { return nil }
func (*Recorder) StopConsuming() error                                          { return nil }
func (*Recorder) Close() error                                                  { return nil }
