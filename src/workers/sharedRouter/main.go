package main

import (
	"os"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/sharedRouter/sharedRouter"
)

func main() {
	os.Exit(sharedRouter.Run())
}
