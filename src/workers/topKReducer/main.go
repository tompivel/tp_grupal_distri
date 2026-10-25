package main

import (
	"os"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/topKReducer/topKReducer"
)

func main() {
	os.Exit(topKReducer.Run())
}
