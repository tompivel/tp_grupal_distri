package dateFilter

import (
	"errors"
	"log/slog"
	"time"

	internalpb "github.com/7574-sistemas-distribuidos/tp-grupal-distri/gen/proto"
	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/sender-receiver-logic/middleware"
	"google.golang.org/protobuf/proto"
)

type DateFilterConfig struct {
	Id               int
	MomHost          string
	MomPort          int
	InputExchange    string
	DateFilterAmount int
	DateFilterPrefix string
}

type DateFilter struct {
	inputQueue     middleware.Middleware
	outputExchange middleware.Middleware
}

func NewDateFilter(config DateFilterConfig) (*DateFilter, error) {
	connSettings := middleware.ConnSettings{
		Hostname: config.MomHost,
		Port:     config.MomPort,
	}
	inputExchange, err := middleware.CreateExchangeMiddleware(
		config.InputExchange,
		[]string{"dateFilter"},
		connSettings,
	)
	if err != nil {
		return nil, err
	}

	outputExchangeRouteKeys := []string{
		"bioFilter", "englishFilter",
	}

	outputExchange, err := middleware.CreateExchangeMiddleware(
		config.DateFilterPrefix,
		outputExchangeRouteKeys,
		connSettings,
	)
	if err != nil {
		_ = inputExchange.Close()
		return nil, err
	}

	return &DateFilter{
		inputQueue:     inputExchange,
		outputExchange: outputExchange,
	}, nil
}

func (filter *DateFilter) Run() {
	if err := filter.inputQueue.StartConsuming(func(
		msg middleware.Message,
		ack func(),
		nack func(),
	) {
		filter.handleMessage(msg, ack, nack)
	}); err != nil {
		slog.Error("While consuming date filter messages", "err", err)
	}
}

func (filter *DateFilter) handleMessage(
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
	case *internalpb.InternalMessage_ProjectedArticle:
		if err := filter.handleDataMessage(&message, payload.ProjectedArticle); err != nil {
			slog.Error("While handling data message", "err", err)
			nack()
			return
		}

	case *internalpb.InternalMessage_EndOfFile:
		if err := filter.handleEndOfFile(&message); err != nil {
			slog.Error("While propagating EOF", "err", err)
			nack()
			return
		}

	default:
		slog.Error("Received unsupported payload in date filter")
		nack()
		return
	}

	ack()
}

func (filter *DateFilter) handleDataMessage(
	input *internalpb.InternalMessage,
	article *internalpb.ProjectedArticle,
) error {
	if article == nil {
		return errors.New("projected article payload is empty")
	}

	year, err := articleYear(article.GetDateModified())
	if err != nil {
		return err
	}

	if year <= 2020 {
		return nil
	}

	dateFiltered := &internalpb.DateFiltered{
		Name:         article.GetName(),
		Url:          article.GetUrl(),
		DateModified: article.GetDateModified(),
		InLanguage:   article.GetInLanguage(),
		Image:        article.GetImage(),
		Sections:     article.GetSections(),
	}

	output := &internalpb.InternalMessage{
		ClientId: input.GetClientId(),
		Payload: &internalpb.InternalMessage_DateFiltered{
			DateFiltered: dateFiltered,
		},
	}

	return filter.send(output)
}

func (filter *DateFilter) handleEndOfFile(
	input *internalpb.InternalMessage,
) error {
	output := &internalpb.InternalMessage{
		ClientId: input.GetClientId(),
		Payload: &internalpb.InternalMessage_EndOfFile{
			EndOfFile: &internalpb.EndOfFile{},
		},
	}

	return filter.send(output)
}

func (filter *DateFilter) send(
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

func articleYear(dateModified string) (int, error) {
	parsedDate, err := time.Parse(time.RFC3339Nano, dateModified)
	if err != nil {
		return 0, errors.New("invalid date_modified: " + dateModified)
	}

	return parsedDate.Year(), nil
}
