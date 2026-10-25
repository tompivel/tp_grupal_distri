package main

import (
	"os"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/wordcounterReducer/wordcounterReducer"
)

func main() {
	os.Exit(wordcounterReducer.Run())
}
