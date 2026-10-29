package dateFilter

import (
	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/common/testmiddleware"
	pb "github.com/7574-sistemas-distribuidos/tp-grupal-distri/gen/proto"
	"google.golang.org/protobuf/proto"
	"testing"
)

func TestCutoff(t *testing.T) {
	for _, tc := range []struct {
		date    string
		want    int
		invalid bool
	}{
		{"2020-12-31T23:59:59.999", 1, false}, {"2021-01-01T00:00:00.000", 0, false}, {"2019-01-01T00:00:00Z", 1, false}, {"2021-01-01T00:00:00+03:00", 0, false}, {"bad", 0, true},
	} {
		t.Run(tc.date, func(t *testing.T) {
			out := &testmiddleware.Recorder{}
			f := &DateFilter{outputExchange: out}
			err := f.handleDataMessage(&pb.InternalMessage{ClientId: "a"}, &pb.ProjectedArticle{DateModified: tc.date, Url: "u"})
			if (err != nil) != tc.invalid || len(out.Messages) != tc.want {
				t.Fatalf("err=%v outputs=%d", err, len(out.Messages))
			}
		})
	}
}
func TestEOFPreservesClient(t *testing.T) {
	out := &testmiddleware.Recorder{}
	f := &DateFilter{outputExchange: out}
	if err := f.handleEndOfFile(&pb.InternalMessage{ClientId: "b"}); err != nil {
		t.Fatal(err)
	}
	var got pb.InternalMessage
	proto.Unmarshal([]byte(out.Messages[0].Body), &got)
	if got.ClientId != "b" || got.GetEndOfFile() == nil {
		t.Fatal(&got)
	}
}
