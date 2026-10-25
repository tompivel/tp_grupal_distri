package imageFetcher

import "github.com/7574-sistemas-distribuidos/tp-grupal-distri/common/worker"

func Run() int {
	return worker.Run("imageFetcher")
}
