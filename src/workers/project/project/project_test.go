package project

import (
	"testing"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/common/testmiddleware"
	internal_pb "github.com/7574-sistemas-distribuidos/tp-grupal-distri/gen/proto"
	common_pb "github.com/7574-sistemas-distribuidos/tp-grupal-distri/gen/proto/common"
	"google.golang.org/protobuf/proto"
)

func TestProjectionAndDuplicates(t *testing.T) {
	out := &testmiddleware.Recorder{}
	p := &Project{outputExchange: out}
	a := &common_pb.Article{Name: "n", Url: "u", DateModified: "2020-01-01T00:00:00.000", Abstract: "a", InLanguage: &common_pb.ArticleLanguage{Identifier: "en"}, Image: &common_pb.ArticleImage{ContentUrl: "i"}}
	for i := 0; i < 2; i++ {
		if err := p.handleDataMessage(&internal_pb.InternalMessage{ClientId: "b"}, a); err != nil {
			t.Fatal(err)
		}
	}
	if len(out.Messages) != 2 {
		t.Fatal("duplicates lost")
	}
	var got internal_pb.InternalMessage
	proto.Unmarshal([]byte(out.Messages[0].Body), &got)
	if got.ClientId != "b" || got.GetProjectedArticle().Abstract != "a" || got.GetProjectedArticle().Image.ContentUrl != "i" {
		t.Fatal(&got)
	}
}
