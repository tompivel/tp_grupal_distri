package main

import (
	"os"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/englishFilter/englishFilter"
)

func main() {
	os.Exit(englishFilter.Run())
}
