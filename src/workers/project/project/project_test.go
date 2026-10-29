package project

import (
	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/common/testmiddleware"
	pb "github.com/7574-sistemas-distribuidos/tp-grupal-distri/gen/proto"
	"google.golang.org/protobuf/proto"
	"testing"
)

func TestProjectionAndDuplicates(t *testing.T) {
	out := &testmiddleware.Recorder{}
	p := &Project{outputExchange: out}
	a := &pb.Article{Name: "n", Url: "u", DateModified: "2020-01-01T00:00:00.000", Abstract: "a", InLanguage: &pb.ArticleLanguage{Identifier: "en"}, Image: &pb.ArticleImage{ContentUrl: "i"}}
	for i := 0; i < 2; i++ {
		if err := p.handleDataMessage(&pb.InternalMessage{ClientId: "b"}, a); err != nil {
			t.Fatal(err)
		}
	}
	if len(out.Messages) != 2 {
		t.Fatal("duplicates lost")
	}
	var got pb.InternalMessage
	proto.Unmarshal([]byte(out.Messages[0].Body), &got)
	if got.ClientId != "b" || got.GetProjectedArticle().Abstract != "a" || got.GetProjectedArticle().Image.ContentUrl != "i" {
		t.Fatal(&got)
	}
}
