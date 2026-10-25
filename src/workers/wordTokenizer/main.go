package main

import (
	"os"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/wordTokenizer/wordTokenizer"
)

func main() {
	os.Exit(wordTokenizer.Run())
}
