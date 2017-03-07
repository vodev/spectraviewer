import os
import io
import tornado.web
import tornado.websocket
from tornado.options import options
from matplotlib.backends.backend_webagg_core import \
    FigureManagerWebAgg, \
    new_figure_manager_given_figure
from matplotlib.figure import Figure
from matplotlib._pylab_helpers import Gcf
import json


class MplJsHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_header('Content-Type', 'application/javascript')
        js = FigureManagerWebAgg.get_javascript()
        self.write(js)


class IndexHandler(tornado.web.RequestHandler):
    def get(self):
        self.render('index.html')


class SpectraViewHandler(tornado.web.RequestHandler):
    async def get(self):
        location = self.get_argument('location', 'filesystem')
        spectra_arg = self.get_argument('spectra', None)
        if not spectra_arg:
            raise tornado.web.HTTPError(400, reason='Missing "spectra" query parameter')
        # expand spectra list
        spectra_list = spectra_arg.split(',')
        spectra_list = list(filter(lambda x: len(x) > 0, map(lambda x: x.strip(), spectra_list)))
        if len(spectra_list) == 0:
            raise tornado.web.HTTPError(400, reason='No spectrum selected')
        # check for location
        if location == 'filesystem':
            print('filesystem')
        elif location == 'jobs':
            print('jobs')
        else:
            raise tornado.web.HTTPError(400, reason='Unknown location: "{}"'.format(location))
        fig = Figure()
        ax = fig.add_subplot(111)
        import numpy as np
        t = np.arange(-5., 5., 0.2)
        ax.plot(t, t ** 2)
        ax.plot(t, t ** 3)
        ax.plot(t, t ** 4)
        ax.set_title('Some title')
        fig_num = id(fig)
        manager = new_figure_manager_given_figure(fig_num, fig)
        Gcf.set_active(manager)
        self.render('figure.html', host=self.request.host, fig_num=fig_num)


class WebSocketHandler(tornado.websocket.WebSocketHandler):
    def open(self, fig_num):
        self.supports_binary = True
        self.manager = Gcf.get_fig_manager(int(fig_num))
        self.manager.add_web_socket(self)
        if hasattr(self, 'set_nodelay'):
            self.set_nodelay(True)

    def on_close(self):
        # todo possible cleanup of figure
        self.manager.remove_web_socket(self)

    def on_message(self, message):
        message = json.loads(message)
        if message['type'] == 'supports_binary':
            self.supports_binary = message['value']
        else:
            self.manager.handle_json(message)

    def send_json(self, content):
        self.write_message(json.dumps(content))

    def send_binary(self, blob):
        if self.supports_binary:
            self.write_message(blob, binary=True)
        else:
            data = 'data:image/png;base64,{}'.format(
                blob.encode('base64').replace('\n', '')
            )
            self.write_message(data)


class DownloadHandler(tornado.web.RequestHandler):
    def get(self, fmt, fig_num):
        manager = Gcf.get_fig_manager(int(fig_num))

        mimetypes = {
            'ps': 'application/postscript',
            'eps': 'application/postscript',
            'pdf': 'application/pdf',
            'svg': 'image/svg+xml',
            'png': 'image/png',
            'jpeg': 'image/jpeg',
            'tif': 'image/tiff',
            'emf': 'application/emf'
        }

        self.set_header('Content-Type', mimetypes.get(fmt, 'binary'))

        buff = io.BytesIO()
        manager.canvas.print_figure(buff, format=fmt)
        self.write(buff.getvalue())


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            tornado.web.URLSpec(r'/viewer/', IndexHandler, name='index'),
            tornado.web.URLSpec(r'/viewer/mpl.js', MplJsHandler, name='mpl'),
            tornado.web.URLSpec(r'/viewer/view', SpectraViewHandler, name='spectra'),
            tornado.web.URLSpec(r'/viewer/([0-9]+)/ws', WebSocketHandler, name='ws'),
            tornado.web.URLSpec(r'/viewer/download.([a-z0-9.]+)/([0-9]+)', DownloadHandler, name='download'),
        ]
        settings = {
            'template_path': os.path.join(os.path.dirname(__file__), 'templates'),
            'static_path': os.path.join(os.path.dirname(__file__), 'static'),
            'debug': True
            # xsrf_cookies=True,
        }
        super(Application, self).__init__(handlers, **settings)