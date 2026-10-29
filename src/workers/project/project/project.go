package project

import (
	"errors"
	"log/slog"

	internalpb "github.com/7574-sistemas-distribuidos/tp-grupal-distri/gen/proto"
	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/sender-receiver-logic/middleware"
	"google.golang.org/protobuf/proto"
)

type ProjectConfig struct {
	Id            int
	MomHost       string
	MomPort       int
	InputQueue    string
	ProjectAmount int
	ProjectPrefix string
}

type Project struct {
	inputQueue     middleware.Middleware
	outputExchange middleware.Middleware
}

func NewProject(config ProjectConfig) (*Project, error) {
	connSettings := middleware.ConnSettings{Hostname: config.MomHost, Port: config.MomPort}

	inputQueue, err := middleware.CreateQueueMiddleware(config.InputQueue, connSettings)
	if err != nil {
		return nil, err
	}

	outputExchangeRouteKeys := []string{"dateFilter", "wordTokenizer"}
	outputExchange, err := middleware.CreateExchangeMiddleware("projected-input", outputExchangeRouteKeys, connSettings)
	if err != nil {
		inputQueue.Close()
		return nil, err
	}

	return &Project{
		inputQueue:     inputQueue,
		outputExchange: outputExchange,
	}, nil
}

func (project *Project) Run() {
	defer project.inputQueue.Close()
	defer project.outputExchange.Close()

	middleware.Consume(project.inputQueue, func(msg middleware.Message, ack, nack func()) {
		project.handleMessage(msg, ack, nack)
	})
}

func (project *Project) handleMessage(msg middleware.Message, ack func(), nack func()) {
	var message internalpb.InternalMessage

	if err := proto.Unmarshal([]byte(msg.Body), &message); err != nil {
		slog.Error("While deserializing message", "err", err)
		nack()
		return
	}

	switch payload := message.GetPayload().(type) {
	case *internalpb.InternalMessage_Article:
		if err := project.handleDataMessage(&message, payload.Article); err != nil {
			slog.Error("While handling data message", "err", err)
			nack()
			return
		}
	case *internalpb.InternalMessage_EndOfFile:
		if err := project.handleEndOfRecordMessage(&message); err != nil {
			slog.Error("While handling end of record message", "err", err)
			nack()
			return
		}
	default:
		slog.Error("Received unsupported project payload")
		nack()
		return
	}

	ack()
}

func (project *Project) handleEndOfRecordMessage(input *internalpb.InternalMessage) error {
	slog.Info("Received End Of Records message")

	data, err := proto.Marshal(&internalpb.InternalMessage{
		ClientId: input.GetClientId(),
		Payload:  &internalpb.InternalMessage_EndOfFile{EndOfFile: &internalpb.EndOfFile{}},
	})
	if err != nil {
		slog.Debug("While serializing EOF message", "err", err)
		return err
	}
	if err := project.outputExchange.Send(middleware.Message{Body: string(data)}); err != nil {
		slog.Debug("While sending EOF message", "err", err)
		return err
	}
	return nil
}

func (project *Project) handleDataMessage(input *internalpb.InternalMessage, article *internalpb.Article) error {
	if article == nil {
		return errors.New("article payload is empty")
	}

	projected := &internalpb.ProjectedArticle{
		Name:         article.GetName(),
		Url:          article.GetUrl(),
		DateModified: article.GetDateModified(),
		Abstract:     article.GetAbstract(),
		InLanguage:   article.GetInLanguage(),
		Image:        article.GetImage(),
		Sections:     article.GetSections(),
	}

	data, err := proto.Marshal(&internalpb.InternalMessage{
		ClientId: input.GetClientId(),
		Payload:  &internalpb.InternalMessage_ProjectedArticle{ProjectedArticle: projected},
	})
	if err != nil {
		return err
	}

	return project.outputExchange.Send(middleware.Message{Body: string(data)})
}
