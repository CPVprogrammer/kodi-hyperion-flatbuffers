'''
		Kodi -> Hyperion - flatbuffers
'''
import xbmc

import socket
import struct

import flatbuffers
import hyperionnet.Register as h_register
import hyperionnet.RawImage as h_rawImage
import hyperionnet.Image as h_image
import hyperionnet.ImageType as h_imageType
import hyperionnet.Clear as h_clear
import hyperionnet.Color as h_color
import hyperionnet.Request as h_request
import hyperionnet.Command as h_command
import hyperionnet.Reply as h_reply

from misc import log
from enum import Enum


class TypeRequest(Enum):
    REGISTER = 1
    IMAGE = 2
    CLEAR = 3
    COLOR = 4


class Hyperion():
    def __init__(self, kodi_settings):
        # get addon settings
        self.settings = kodi_settings
        self.img_width = self.settings.capture_width
        self.img_height = self.settings.capture_height

        # kodi
        self.first_capture = True

        # create flatbuffers builder
        self.builder = flatbuffers.Builder(0)

        # connect to hyperion
        self.socket_hyperion = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_hyperion.settimeout(2)
        self.socket_connected = False
        self.connect_socket()


    def __del__(self):
        try:
            self.socket_hyperion.close()
        except:
            pass


    def connect_socket(self):
        ''' create a socket connection to hyperion
        '''
        try:
            log("hyperion address: "+ self.settings.address +" port: " +str(self.settings.port))
            self.socket_hyperion.connect((self.settings.address, self.settings.port))
            self.socket_connected = True
        except Exception as e:
            log("hyperion connection: "+ str(e))


    def capture(self):
        ''' capture an image from kodi and send to hyperion
        '''
        if self.first_capture:
            self.create_register('Kodi', 150)
            self.first_capture = False

        self.kodi_capture = xbmc.RenderCapture()
        self.kodi_capture.capture(self.img_width, self.img_height)

        # Format of captured image: 'BGRA'
        image_data = self.kodi_capture.getImage()

        if len(image_data) > 0:
            # BGRA --> RGB
            del image_data[3::4]
            image_data[0::3], image_data[2::3] = image_data[2::3], image_data[0::3]

            self.create_image(image_data, self.img_width, self.img_height, -1)

            #limit the maximum number of frames sent to hyperion
            xbmc.sleep(int(1. / self.settings.framerate * 1000))


    def create_register(self, origin, priority):
        ''' origin:string (required);
            priority:int;

            https://docs.hyperion-project.org/en/api/guidelines.html#priority-guidelines
        '''
        register_name = self.builder.CreateString(origin)

        h_register.Start(self.builder)
        h_register.AddOrigin(self.builder, register_name)
        h_register.AddPriority(self.builder, priority)
        self.new_register = h_register.End(self.builder)
        self.create_request(TypeRequest.REGISTER)


    def create_rawImage(self, image_data, img_width, img_height):
        ''' data:[ubyte];
            width:int = -1;
            height:int = -1;
        '''
        data_len = len(image_data)

        h_rawImage.StartDataVector(self.builder, data_len)

        # Note: Since we prepend the bytes, this loop iterates in reverse order.
        for i in reversed(range(0, data_len)):
            self.builder.PrependByte(image_data[i])

        data_vector = self.builder.EndVector()

        h_rawImage.Start(self.builder)        
        h_rawImage.AddData(self.builder, data_vector)
        h_rawImage.AddWidth(self.builder, img_width)
        h_rawImage.AddHeight(self.builder, img_height)
        new_rawImage = h_rawImage.End(self.builder)

        return new_rawImage


    def create_image(self, image_data, img_width, img_height, duration):
        ''' data:ImageType (required);
            duration:int = -1;

            union ImageType {RawImage}
        '''
        raw_image = self.create_rawImage(image_data, img_width, img_height)

        h_image.Start(self.builder)
        h_image.AddDataType(self.builder, h_imageType.ImageType().RawImage)
        h_image.AddData(self.builder, raw_image)
        h_image.AddDuration(self.builder, duration)
        self.new_image = h_image.End(self.builder)
        self.create_request(TypeRequest.IMAGE)


    def create_clear(self, priority):
        ''' priority:int;
        '''
        h_clear.Start(self.builder)
        h_clear.AddPriority(self.builder, priority)
        self.new_clear = h_clear.End(self.builder)
        self.create_request(TypeRequest.CLEAR)


    def create_color(self, data, duration):
        ''' data:int = -1;  --> Color ARGB (0x00RRGGBB)
            duration:int = -1;
        '''
        h_color.Start(self.builder)
        h_color.AddData(self.builder, data)
        h_color.AddDuration(self.builder, duration)
        self.new_color = h_color.End(self.builder)
        self.create_request(TypeRequest.COLOR)


    def create_request(self, type_request):
        ''' command:Command (required);

            union Command {Color, Image, Clear, Register}
        '''
        h_request.Start(self.builder)

        if (type_request is TypeRequest.REGISTER):
            h_request.AddCommandType(self.builder, h_command.Command().Register)
            h_request.AddCommand(self.builder, self.new_register)

        elif (type_request is TypeRequest.IMAGE):
            h_request.AddCommandType(self.builder, h_command.Command().Image)
            h_request.AddCommand(self.builder, self.new_image)

        elif (type_request is TypeRequest.CLEAR):
            h_request.AddCommandType(self.builder, h_command.Command().Clear)
            h_request.AddCommand(self.builder, self.new_clear)

        elif (type_request is TypeRequest.COLOR):
            h_request.AddCommandType(self.builder, h_command.Command().Color)
            h_request.AddCommand(self.builder, self.new_color)

        new_request = h_request.End(self.builder)
        self.builder.Finish(new_request)
        
        self.flatbuf_data = self.builder.Output()
        
        self.send_recv_data()


    def send_recv_data(self):
        ''' send flatbuffers to hyperion
            recv reply from hyperion
        '''
        # send data to Hyperion server
        binarySize = struct.pack(">I", len(self.flatbuf_data))
        self.socket_hyperion.sendall(binarySize)
        self.socket_hyperion.sendall(self.flatbuf_data);

        # receive a reply from Hyperion server
        size = struct.unpack(">I", self.socket_hyperion.recv(4))[0]
        buf_recv = self.socket_hyperion.recv(size)

        flatbuf_reply = h_reply.Reply.GetRootAs(buf_recv, 0)
        
        if (flatbuf_reply.Error() is not None):
            log("error: "+ str(flatbuf_reply.Error()))
            log("video: "+ str(flatbuf_reply.Video()))
            log("registered: "+ str(flatbuf_reply.Registered()))
