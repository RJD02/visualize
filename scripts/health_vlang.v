module main

import vweb

struct App {
	vweb.Context
}

@['/health']
fn (mut app App) health() vweb.Result {
	return app.text('ok')
}

fn main() {
	vweb.run(App{}, 8081)
}
