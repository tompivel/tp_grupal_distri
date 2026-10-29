package gateway

import (
	"log/slog"
	"net"
	"os"
	"os/signal"
	"sync/atomic"
	"syscall"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/clientregistry"
	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/common/fruititem"
	internal_pb "github.com/7574-sistemas-distribuidos/tp-grupal-distri/gen/proto"
	common_pb "github.com/7574-sistemas-distribuidos/tp-grupal-distri/gen/proto/common"
	external_pb "github.com/7574-sistemas-distribuidos/tp-grupal-distri/gen/proto/external"
	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/messagehandler"
	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/sender-receiver-logic/middleware"
	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/sender-receiver-logic/protocol/external"
	"google.golang.org/protobuf/proto"
)

type GatewayConfig struct {
	InputQueueName  string
	OutputQueueName string
	ServerHost      string
	ServerPort      string
	MomHost         string
	MomPort         int
}

type Gateway struct {
	registry    clientregistry.ClientRegistry
	inputQueue  middleware.Middleware
	outputQueue middleware.Middleware
	listener    net.Listener
	running     atomic.Bool
}

func NewGateway(config GatewayConfig) (*Gateway, error) {
	connSettings := middleware.ConnSettings{Hostname: config.MomHost, Port: config.MomPort}

	inputQueue, err := middleware.CreateQueueMiddleware(config.OutputQueueName, connSettings)
	if err != nil {
		return nil, err
	}

	outputQueue, err := middleware.CreateQueueMiddleware(config.InputQueueName, connSettings)
	if err != nil {
		inputQueue.Close()
		return nil, err
	}

	listener, err := net.Listen("tcp", config.ServerHost+":"+config.ServerPort)
	if err != nil {
		inputQueue.Close()
		outputQueue.Close()
		return nil, err
	}

	gateway := &Gateway{outputQueue: outputQueue, inputQueue: inputQueue, listener: listener}
	gateway.running.Store(true)
	return gateway, nil
}

func (gateway *Gateway) Run() error {
	defer gateway.listener.Close()

	go gateway.outputQueue.StartConsuming(func(msg middleware.Message, ack, nack func()) {
		gateway.handleClientResponse(msg, ack, nack)
	})
	go gateway.handleSignals()

	slog.Info("Accepting connections...")

	for {
		conn, err := gateway.listener.Accept()
		if err != nil {
			if !gateway.running.Load() {
				break
			}
			return err
		}

		slog.Info("Client connected...")

		handler := messagehandler.NewMessageHandler()
		client := clientregistry.ClientState{Conn: conn, Handler: &handler}
		gateway.registry.Add(client)

		go gateway.handleClientRequest(client)
	}

	gateway.outputQueue.StopConsuming()
	gateway.registry.WithLock(func(clients []clientregistry.ClientState) {
		for _, client := range clients {
			client.Conn.Close()
		}
	})
	return nil
}

func (gateway *Gateway) handleSignals() {
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, syscall.SIGINT, syscall.SIGTERM)
	<-signals
	slog.Info("SIGTERM signal received")
	gateway.running.Store(false)
	gateway.listener.Close()
}

func (gateway *Gateway) handleClientRequest(client clientregistry.ClientState) {
	for {
		message, err := external.ReadMessage(client.Conn, external.Any)
		if err != nil {
			slog.Debug("While reading client message", "err", err)
			return
		}

		switch payload := message.GetPayload().(type) {
		case *external_pb.ExternalMessage_Article:
			if err := gateway.handleArticleMessage(client, payload.Article); err != nil {
				slog.Debug("While handling article message", "err", err)
				return
			}

		case *external_pb.ExternalMessage_EndOfFile:
			if err := gateway.handleEndOfRecordsMessage(client); err != nil {
				slog.Debug("While handling end of records message", "err", err)
				return
			}
			return

		default:
			slog.Debug("Received unexpected client message")
			return
		}
	}
}

func (gateway *Gateway) handleClientResponse(msg middleware.Message, ack func(), nack func()) {
	clientIndex := -1

	gateway.registry.WithLock(func(clients []clientregistry.ClientState) {
		for i, client := range clients {
			fruitTop, err := client.Handler.DeserializeResultMessage(&msg)
			if err != nil {
				slog.Debug("While reading from output queue", "err", err)
				nack()
				gateway.outputQueue.StopConsuming()
				return
			}

			if fruitTop == nil {
				continue
			}

			if err := external.WriteFruitTop(client.Conn, fruitTop); err != nil {
				slog.Debug("While writing FRUIT_TOP message", "err", err)
				return
			}
			msgType, err := external.ReadMsgType(client.Conn)
			if err != nil {
				slog.Debug("While reading message type", "err", err)
				return
			}
			if msgType != external.Ack {
				slog.Debug("Expected ACK message")
				return
			}
			clientIndex = i
			return
		}
		slog.Warn("No client handler could process this message")
		nack()
	})

	if clientIndex >= 0 {
		gateway.registry.Remove(clientIndex)
		ack()
		return
	}
}

func (gateway *Gateway) handleArticleMessage(client clientregistry.ClientState, article *common_pb.Article) error {
	msg := &internal_pb.InternalMessage{
		ClientId: "client", // TODO: use unique id for each client
		Payload: &internal_pb.InternalMessage_Article{
			Article: article,
		},
	}

	serializedMsg, err := proto.Marshal(msg)
	if err != nil {
		slog.Debug("While serializing data message", "err", err)
		return err
	}

	if err := gateway.inputQueue.Send(middleware.Message{Body: string(serializedMsg)}); err != nil {
		slog.Debug("While sending data message", "err", err)
		return err
	}
	if err := external.WriteAck(client.Conn); err != nil {
		slog.Debug("While writing ACK message", "err", err)
		return err
	}
	return nil
}

func (gateway *Gateway) handleFruitRecordMessage(client clientregistry.ClientState) error {
	fruitRecord, err := external.ReadFruitRecord(client.Conn)
	if err != nil {
		slog.Debug("While reading FRUIT_RECORD", "err", err)
		return err
	}
	message, err := client.Handler.SerializeDataMessage([]fruititem.FruitItem{*fruitRecord})
	if err != nil {
		slog.Debug("While serializing data message", "err", err)
		return err
	}
	if err := gateway.inputQueue.Send(*message); err != nil {
		slog.Debug("While sending data message", "err", err)
		return err
	}
	if err := external.WriteAck(client.Conn); err != nil {
		slog.Debug("While writing ACK message", "err", err)
		return err
	}
	return nil
}

func (gateway *Gateway) handleEndOfRecordsMessage(client clientregistry.ClientState) error {
	slog.Info("Received END_OF_RECORDS message")
	message := &internal_pb.InternalMessage{
		ClientId: "client", // TODO: use unique id for each client
		Payload: &internal_pb.InternalMessage_EndOfFile{
			EndOfFile: &internal_pb.EndOfFile{},
		},
	}
	serializedMessage, err := proto.Marshal(message)
	if err != nil {
		slog.Debug("While serializing END_OF_RECORDS message", "err", err)
		return err
	}
	if err := gateway.inputQueue.Send(middleware.Message{Body: string(serializedMessage)}); err != nil {
		slog.Debug("While sending eof message", "err", err)
		return err
	}
	if err := external.WriteAck(client.Conn); err != nil {
		slog.Debug("While writing ACK message", "err", err)
		return err
	}
	return nil
}
