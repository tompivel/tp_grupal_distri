package main

import (
	"os"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/imageFetcher/imageFetcher"
)

func main() {
	os.Exit(imageFetcher.Run())
}
