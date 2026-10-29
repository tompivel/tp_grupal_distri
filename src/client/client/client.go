package client

import (
	"encoding/csv"
	"errors"
	"io"
	"log/slog"
	"net"
	"os"
	"os/signal"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/model"
	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/sender-receiver-logic/protocol/external"
	"github.com/parquet-go/parquet-go"
)

const connectionAttempts = 3
const connectionAttemptsDelayMs = 300

type ClientConfig struct {
	ServerHost string
	ServerPort string
	InputFile  string
	OutputFile string
}

type Client struct {
	conn    net.Conn
	running atomic.Bool
	config  ClientConfig
}

func NewClient(config ClientConfig) (*Client, error) {
	conn, err := connectToServer(config.ServerHost, config.ServerPort)
	if err != nil {
		return nil, err
	}

	client := &Client{conn: conn, config: config}
	client.running.Store(true)
	return client, nil
}

func connectToServer(host, port string) (net.Conn, error) {
	var err error
	var conn net.Conn

	for range connectionAttempts {
		conn, err = net.Dial("tcp", host+":"+port)
		if err != nil {
			slog.Warn("Retrying connection...")
			time.Sleep(connectionAttemptsDelayMs * time.Millisecond)
			continue
		}
		break
	}

	return conn, err
}

func (client *Client) Run() error {
	defer client.conn.Close()
	go client.handleSignals()

	if err := client.sendArticles(); err != nil {
		if client.running.Load() {
			return err
		}
		return nil
	}

	if err := client.recvResults(); err != nil {
		if client.running.Load() {
			return err
		}
		return nil
	}

	return nil
}

func (client *Client) handleSignals() {
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, syscall.SIGINT, syscall.SIGTERM)
	<-signals
	slog.Info("SIGTERM signal received")
	client.running.Store(false)
	client.conn.Close()
}

func (client *Client) expectMsgType(expectedMsgType external.MsgType) error {
	msgType, err := external.ReadMsgType(client.conn)
	if err != nil {
		slog.Debug("Error while reading message type", "err", err)
		return err
	}
	if msgType != expectedMsgType {
		return errors.New("Unexpected message type")
	}
	return nil
}

func (client *Client) sendArticles() error {
	file, err := os.Open(client.config.InputFile)
	if err != nil {
		slog.Debug("Error while runninging input file", "err", err)
		return err
	}
	defer file.Close()

	reader := parquet.NewGenericReader[model.ParquetArticle](file)
	defer reader.Close()

	batch := make([]model.ParquetArticle, 1)

	for {
		n, err := reader.Read(batch)
		if n > 0 {
			article, err := batch[0].ToProto()

			if err != nil {
				return err
			}

			if err := external.WriteArticle(client.conn, article); err != nil {
				return err
			}

			/*
				TODO: Implement id for messages to link them to ack

				if _, err := external.ReadMessage(client.conn, external.Ack); err != nil {
					return err
				}
			*/
		}

		if err != nil {
			if err == io.EOF {
				break
			}
			return err
		}
	}

	if err := external.WriteEndOfRecords(client.conn); err != nil {
		return err
	}
	/*
		if _, err := external.ReadMessage(client.conn, external.Ack); err != nil {
			return err
		}
	*/

	return nil
}

func (client *Client) recvResults() error {
	outputFile, err := os.Create(client.config.OutputFile)
	if err != nil {
		slog.Debug("Error while creating output file", "err", err)
		return err
	}
	defer outputFile.Close()
	outputFileWriter := csv.NewWriter(outputFile)

	for {
		message, err := external.ReadMessage(client.conn, external.Any)
		if err != nil {
			return err
		}

		if resultBatch := message.GetResultBatch(); resultBatch != nil {
			for _, result := range resultBatch.GetResults() {
				q1Result := result.GetQ1()
				if q1Result == nil {
					return errors.New("result batch contains a non-Q1 result")
				}
				if err := outputFileWriter.Write([]string{q1Result.GetUrl(), q1Result.GetDateModified()}); err != nil {
					slog.Debug("Error while writing output file", "err", err)
					return err
				}
			}
			if err := outputFileWriter.Error(); err != nil {
				return err
			}
			/*
				if err := external.WriteAck(client.conn); err != nil {
					slog.Debug("Error while writing ack message", "err", err)
					return err
				}
			*/
		} else if message.GetAllFinished() != nil {
			return outputFileWriter.Error()
		} else {
			return errors.New("expected ResultBatch or AllFinished message")
		}
	}
}
