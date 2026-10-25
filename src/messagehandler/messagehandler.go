package messagehandler

import (
	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/common/fruititem"
	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/sender-receiver-logic/middleware"
	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/sender-receiver-logic/protocol/inner"
)

type MessageHandler struct {
	clientID   string
	totalItems uint64
}

func NewMessageHandler() MessageHandler {
	return MessageHandler{}
}

func (h *MessageHandler) SerializeDataMessage(records []fruititem.FruitItem) (*middleware.Message, error) {
	h.totalItems += uint64(len(records))
	return inner.SerializeMessage(h.clientID, records)
}

func (h *MessageHandler) SerializeEOFMessage() (*middleware.Message, error) {
	return inner.SerializeEOFMessage(h.clientID, h.totalItems)
}

func (h *MessageHandler) DeserializeResultMessage(message *middleware.Message) ([]fruititem.FruitItem, error) {
	_, records, _, _, err := inner.DeserializeMessage(message)
	return records, err
}
