package englishFilter

import (
	"log/slog"

	internalpb "github.com/7574-sistemas-distribuidos/tp-grupal-distri/gen/proto"
	externalpb "github.com/7574-sistemas-distribuidos/tp-grupal-distri/gen/proto/external"
	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/sender-receiver-logic/middleware"
	"google.golang.org/protobuf/proto"
)

type EnglishFilterConfig struct {
	Id                  int
	MomHost             string
	MomPort             int
	InputExchange       string
	EnglishFilterAmount int
	EnglishFilterPrefix string
}

type EnglishFilter struct {
	inputExchange  middleware.Middleware
	outputExchange middleware.Middleware
}

func NewEnglishFilter(config EnglishFilterConfig) (*EnglishFilter, error) {
	connSettings := middleware.ConnSettings{
		Hostname: config.MomHost,
		Port:     config.MomPort,
	}

	inputExchange, err := middleware.CreateExchangeMiddleware(
		config.InputExchange,
		[]string{"englishFilter"},
		connSettings,
	)
	if err != nil {
		return nil, err
	}

	outputExchange, err := middleware.CreateQueueMiddleware(
		"results", // @TO DO: No debería enviar directamente a la cola de resultados
		connSettings,
	)
	if err != nil {
		_ = inputExchange.Close()
		return nil, err
	}

	return &EnglishFilter{
		inputExchange:  inputExchange,
		outputExchange: outputExchange,
	}, nil
}

func (filter *EnglishFilter) Run() {
	if err := filter.inputExchange.StartConsuming(func(
		msg middleware.Message,
		ack func(),
		nack func(),
	) {
		filter.handleMessage(msg, ack, nack)
	}); err != nil {
		slog.Error("While consuming English filter messages", "err", err)
	}
}

func (filter *EnglishFilter) handleMessage(
	msg middleware.Message,
	ack func(),
	nack func(),
) {
	var message internalpb.InternalMessage

	if err := proto.Unmarshal([]byte(msg.Body), &message); err != nil {
		slog.Error("While deserializing message", "err", err)
		nack()
		return
	}

	switch payload := message.GetPayload().(type) {
	case *internalpb.InternalMessage_DateFiltered:
		if err := filter.handleDataMessage(&message, payload.DateFiltered); err != nil {
			slog.Error("While handling data message", "err", err)
			nack()
			return
		}

	case *internalpb.InternalMessage_EndOfFile:
		if err := filter.handleEndOfFile(); err != nil {
			slog.Error("While propagating EOF", "err", err)
			nack()
			return
		}

	default:
		slog.Error("Received unsupported payload in English filter")
		nack()
		return
	}

	ack()
}

func (filter *EnglishFilter) handleDataMessage(
	input *internalpb.InternalMessage,
	article *internalpb.DateFiltered,
) error {
	if article == nil {
		return nil
	}

	if article.GetInLanguage().GetIdentifier() != "en" {
		return nil
	}

	output := &internalpb.InternalMessage{
		ClientId: input.GetClientId(),
		Payload: &internalpb.InternalMessage_DateFiltered{
			DateFiltered: article,
		},
	}

	return filter.send(output)
}

func (filter *EnglishFilter) handleEndOfFile() error {
	// TODO: Move AllFinished generation to resultCollector once final aggregation
	// is implemented.
	output := &externalpb.ExternalMessage{
		Payload: &externalpb.ExternalMessage_AllFinished{
			AllFinished: &externalpb.AllFinished{},
		},
	}

	data, err := proto.Marshal(output)
	if err != nil {
		return err
	}

	return filter.outputExchange.Send(middleware.Message{
		Body: string(data),
	})
}

func (filter *EnglishFilter) send(
	message *internalpb.InternalMessage,
) error {
	data, err := proto.Marshal(message)
	if err != nil {
		return err
	}

	return filter.outputExchange.Send(middleware.Message{
		Body: string(data),
	})
}
