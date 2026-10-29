package englishFilter

import (
	"errors"
	"testing"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/common/testmiddleware"
	internal_pb "github.com/7574-sistemas-distribuidos/tp-grupal-distri/gen/proto"
	common_pb "github.com/7574-sistemas-distribuidos/tp-grupal-distri/gen/proto/common"
	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/sender-receiver-logic/middleware"
	"google.golang.org/protobuf/proto"
)

func TestLanguageDuplicatesAndEOF(t *testing.T) {
	out := &testmiddleware.Recorder{}
	f := &EnglishFilter{outputExchange: out}
	for _, lang := range []string{"en", "fr", "en", ""} {
		if err := f.handleDataMessage(&internal_pb.InternalMessage{ClientId: "a"}, &internal_pb.DateFiltered{Url: "u", InLanguage: &common_pb.ArticleLanguage{Identifier: lang}}); err != nil {
			t.Fatal(err)
		}
	}
	if len(out.Messages) != 2 {
		t.Fatalf("duplicates lost or language leaked: %d", len(out.Messages))
	}
	if err := f.handleEndOfFile(&internal_pb.InternalMessage{ClientId: "a"}); err != nil {
		t.Fatal(err)
	}
	var eof internal_pb.InternalMessage
	proto.Unmarshal([]byte(out.Messages[2].Body), &eof)
	if eof.ClientId != "a" || eof.GetEndOfFile() == nil {
		t.Fatal(&eof)
	}
}
func TestPublishFailureDoesNotACK(t *testing.T) {
	f := &EnglishFilter{outputExchange: &testmiddleware.Recorder{Err: errors.New("failure")}}
	msg, _ := proto.Marshal(&internal_pb.InternalMessage{ClientId: "a", Payload: &internal_pb.InternalMessage_EndOfFile{EndOfFile: &internal_pb.EndOfFile{}}})
	ack, nack := false, false
	f.handleMessage(middleware.Message{Body: string(msg)}, func() { ack = true }, func() { nack = true })
	if ack || !nack {
		t.Fatal("failed publish acknowledged")
	}
}
