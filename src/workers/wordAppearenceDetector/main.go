package main

import (
	"os"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/wordAppearenceDetector/wordAppearenceDetector"
)

func main() {
	os.Exit(wordAppearenceDetector.Run())
}
