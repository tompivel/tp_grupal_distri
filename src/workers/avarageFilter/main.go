package main

import (
	"os"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/avarageFilter/avarageFilter"
)

func main() {
	os.Exit(avarageFilter.Run())
}
