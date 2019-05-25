# -*- coding: utf-8; -*-
"""
Copyright (c) 2018 Rolf Hempel, rolf6419@gmx.de

This file is part of the PlanetarySystemStacker tool (PSS).
https://github.com/Rolf-Hempel/PlanetarySystemStacker

PSS is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with PSS.  If not, see <http://www.gnu.org/licenses/>.

"""

from glob import glob
from os import path, remove
from pathlib import Path
from time import time

import numpy as np
from cv2 import imread, VideoCapture, CAP_PROP_FRAME_COUNT, cvtColor, COLOR_BGR2GRAY, \
    COLOR_BGR2RGB, GaussianBlur, Laplacian, CV_32F, COLOR_RGB2BGR, imwrite, convertScaleAbs, \
    CAP_PROP_POS_FRAMES, IMREAD_GRAYSCALE, IMREAD_UNCHANGED
from math import ceil
from scipy import misc

from configuration import Configuration
from exceptions import TypeError, ShapeError, ArgumentError, WrongOrderingError
from frames_old import FramesOld


class VideoReader(object):
    """
    The VideoReader deals with the import of frames from a video file. Frames can be read either
    consecutively, or at an arbitrary frame index. Eventually, all common video types (such as .avi,
    .ser, .mov) should be supported.
    """

    def __init__(self):
        """
        Create the VideoReader object and initialize instance variables.
        """

        self.opened = False
        self.just_opened = False
        self.last_read = None
        self.last_frame_read = None
        self.frame_count = None
        self.shape = None
        self.color = None
        self.convert_to_grayscale = False
        self.dtype = None

    def open(self, file_path, convert_to_grayscale=False):
        """
        Initialize the VideoReader object and return parameters with video metadata.
         Throws an IOError if the video file format is not supported.

        :param file_path: Full name of the video file.
        :param convert_to_grayscale: If True, convert color frames to grayscale;
                                     otherwise return RGB color frames.
        :return: (frame_count, color, dtype, shape) with
                 frame_count: Total number of frames in video.
                 color: True, if frames are in color; False otherwise.
                 dtype: Numpy type, either uint8 or uint16
                 shape: Tuple with the shape of a single frame; (num_px_y, num_px_x, 3) for color,
                        (num_px_y, num_px_x) for B/W.
        """

        try:
            # Create the VideoCapture object.
            self.cap = VideoCapture(file_path)

            # Read the first frame.
            ret, self.last_frame_read = self.cap.read()
            if not ret:
                raise IOError("Error in reading first video frame")

            # Look up video metadata.
            self.last_read = 0
            self.frame_count = int(self.cap.get(CAP_PROP_FRAME_COUNT))
            self.shape = self.last_frame_read.shape
            self.color = (len(self.shape) == 3)
            self.dtype = self.last_frame_read.dtype
        except:
            raise IOError("Error in reading first video frame")

        # If file is in color mode and grayscale output is requested, do the conversion and change
        # metadata.
        if self.color:
            if convert_to_grayscale:
                # Remember to do the conversion when reading frames later on.
                self.convert_to_grayscale = True
                self.last_frame_read = cvtColor(self.last_frame_read, COLOR_BGR2GRAY)
                self.color = False
                self.shape = self.last_frame_read.shape
            else:
                # If color mode should stay, change image read by OpenCV into RGB.
                self.last_frame_read = cvtColor(self.last_frame_read, COLOR_BGR2RGB)

        self.opened = True
        self.just_opened = True

        # Return the metadata.
        return self.frame_count, self.color, self.dtype, self.shape

    def read_frame(self, index=None):
        """
        Read a single frame from the video.

        :param index: Frame index (optional). If no index is specified, the next frame is read.
                      At the first invocation, this is frame number 0.
        :return: Numpy array containing the frame. For B/W, the shape is (num_px_y, num_px_x).
                 For a color video, it is (num_px_y, num_px_x, 3). The type is uint8 or uint16 for
                 8 or 16 bit resolution.
        """

        if not self.opened:
            raise WrongOrderingError(
                "Error: Attempt to read video frame before opening VideoReader")

        # Special case: first call after initialization.
        if self.just_opened:
            self.just_opened = False

            # Frame 0 has been read during initialization. Not necessary to read it again.
            if index is None or index == 0:
                return self.last_frame_read
            # Otherwise set the frame pointer to the specified position.
            else:
                self.cap.set(CAP_PROP_POS_FRAMES, index)
                self.last_read = index

        # General case: not the first call.
        else:

            # Consecutive reading. Just increment the frame pointer.
            if index is None:
                self.last_read += 1

            # An index is specified explicitly. If it is the same as at last call, just return the
            # last frame.
            elif index == self.last_read:
                return self.last_frame_read

            # Some other frame was specified explicitly. If it is the next frame after the one read
            # last time, the frame pointer does not have to be set.
            else:
                if index != self.last_read + 1:
                    self.cap.set(CAP_PROP_POS_FRAMES, index)
                self.last_read = index

        # A new frame has to be read. First check if the index is not out of bounds.
        if 0 <= self.last_read < self.frame_count:
            try:
                # Read the next frame.
                ret, self.last_frame_read = self.cap.read()
                if not ret:
                    raise IOError("Error in reading video frame, index: " + str(index))
            except:
                raise IOError("Error in reading video frame, index: " + str(index))

            # Do the conversion to grayscale or into RGB color if necessary.
            if self.convert_to_grayscale:
                self.last_frame_read = cvtColor(self.last_frame_read, COLOR_BGR2GRAY)
            elif self.color:
                self.last_frame_read = cvtColor(self.last_frame_read, COLOR_BGR2RGB)
        else:
            raise ArgumentError("Error in reading video frame, index " + str(index) +
                                " is out of bounds")

        return self.last_frame_read

    def close(self):
        """
        Close the VideoReader object.

        :return:
        """

        self.cap.release()
        self.opened = False


class ImageReader(object):
    """
    The ImageReader deals with the import of frames from a list of single images. Frames can
    be read either consecutively, or at an arbitrary frame index. It is assumed that the
    lexicographic order of file names corresponds to their chronological order. Eventually, all
    common image types (such as .tiff, .png, .jpg) should be supported.
    """

    def __init__(self):
        """
        Create the ImageReader object and initialize instance variables.
        """

        self.opened = False
        self.just_opened = False
        self.last_read = None
        self.last_frame_read = None
        self.frame_count = None
        self.shape = None
        self.color = None
        self.convert_to_grayscale = False
        self.dtype = None

    def open(self, file_path_list, convert_to_grayscale=False):
        """
        Initialize the ImageReader object and return parameters with image metadata.

        :param file_path_list: List with path names to the image files.
        :param convert_to_grayscale: If True, convert color frames to grayscale;
                                     otherwise return RGB color frames.
        :return: (frame_count, color, dtype, shape) with
                 frame_count: Total number of frames.
                 color: True, if frames are in color; False otherwise.
                 dtype: Numpy type, either uint8 or uint16
                 shape: Tuple with the shape of a single frame; (num_px_y, num_px_x, 3) for color,
                        (num_px_y, num_px_x) for B/W.
        """

        self.file_path_list = file_path_list

        try:
            self.frame_count = len(self.file_path_list)

            if convert_to_grayscale:
                self.last_frame_read = imread(self.file_path_list[0], IMREAD_GRAYSCALE)
                # Remember to do the conversion when reading frames later on.
                self.convert_to_grayscale = True
            else:
                self.last_frame_read = imread(self.file_path_list[0], IMREAD_UNCHANGED)

            # Look up metadata.
            self.last_read = 0
            self.shape = self.last_frame_read.shape
            self.color = (len(self.shape) == 3)
            self.dtype = self.last_frame_read.dtype
        except:
            raise IOError("Error in reading first frame")

        # If in color mode, swap B and R channels to convert from cv2 to standard RGB.
        if self.color:
            self.last_frame_read = cvtColor(self.last_frame_read, COLOR_BGR2RGB)

        self.opened = True
        self.just_opened = True

        # Return the metadata.
        return self.frame_count, self.color, self.dtype, self.shape

    def read_frame(self, index=None):
        """
        Read a single frame.

        :param index: Frame index (optional). If no index is specified, the next frame is read.
                      At the first invocation, this is frame number 0.
        :return: Numpy array containing the frame. For B/W, the shape is (num_px_y, num_px_x).
                 For a color video, it is (num_px_y, num_px_x, 3). The type is uint8 or uint16 for
                 8 or 16 bit resolution.
        """

        if not self.opened:
            raise WrongOrderingError(
                "Error: Attempt to read image file frame before opening ImageReader")

        # Special case: first call after initialization.
        if self.just_opened:
            self.just_opened = False

            # Frame 0 has been read during initialization. Not necessary to read it again.
            if index is None or index == 0:
                return self.last_frame_read

        # General case: not the first call.
        else:

            # Consecutive reading. Just increment the frame index.
            if index is None:
                self.last_read += 1

            # An index is specified explicitly. If it is the same as at last call, just return the
            # last frame.
            elif index == self.last_read:
                return self.last_frame_read

            # Some other frame was specified explicitly.
            else:
                self.last_read = index

        # A new frame has to be read. First check if the index is not out of bounds.
        if 0 <= self.last_read < self.frame_count:
            try:
                if self.convert_to_grayscale:
                    self.last_frame_read = imread(self.file_path_list[self.last_read],
                                                  IMREAD_GRAYSCALE)
                else:
                    self.last_frame_read = imread(self.file_path_list[self.last_read],
                                                  IMREAD_UNCHANGED)
            except:
                raise IOError("Error in reading image frame, index: " + str(index))
        else:
            raise ArgumentError("Error in reading image frame, index: " + str(index) +
                                " is out of bounds")

        # Check if the metadata match.
        shape = self.last_frame_read.shape
        color = (len(shape) == 3)

        # Check if all images have matching metadata.
        if color != self.color:
            raise ShapeError(
                "Mixing grayscale and color images not supported, index: " + str(index))
        elif shape != self.shape:
            raise ShapeError("Images have different size, index: " + str(index))
        elif self.last_frame_read.dtype != self.dtype:
            raise TypeError("Images have different type, index: " + str(index))

        return self.last_frame_read

    def close(self):
        """
        Close the ImageReader object.

        :return:
        """

        self.opened = False


class Frames(object):
    """
        This object stores the image data of all frames. Four versions of the original frames are
        used throughout the data processing workflow. They are (re-)used in the folliwing phases:
        1. Original (color) frames, type: uint8 / uint16
            - Frame stacking ("stack_frames.stack_frames")
        2. Monochrome version of 1., type: uint8 / uint16
            - Computing the average frame (only average frame subset, "align_frames.average_frame")
        3. Gaussian blur added to 2., type: type: uint16
            - Aligning all frames ("align_frames.align_frames")
            - Frame stacking ("stack_frames.stack_frames")
        4. Down-sampled Laplacian of 3., type: uint8
            - Overall image ranking ("rank_frames.frame_score")
            - Ranking frames at alignment points("alignment_points.compute_frame_qualities")

        Buffering at various levels is available. It is controlled with four flags set at object
        initialization time.

        A complete PSS execution processes all "n" frames in four complete passes. Additionally,
        in module "align_frames" there are some extra accesses:

        1. In "rank_frames.frame_score": Access to all "Laplacians of Gaussian" (frame 0 to n-1)
           In "align_frames.select_alignment_rect and .align_frames": Access to the Gaussian of the
           best frame.
        2. In "align_frames.align_frames": Access to all Gaussians (frame 0 to n-1)
           In "align_frames.average_frame": Access to the monochrome frames of the best images for
           averaging
        3. In "alignment_points.compute_frame_qualities": Access to all "Laplacians of Gaussian"
           (frame 0 to n-1)
        4. In "stack_frames.stack_frames": Access to all frames + Gaussians (frame 0 to n-1)

    """

    def __init__(self, configuration, names, type='video', convert_to_grayscale=False,
                 progress_signal=None, buffer_original=True, buffer_monochrome=False,
                 buffer_gaussian=True, buffer_laplacian=True):
        """
        Initialize the Frame object, and read all images. Images can be stored in a video file or
        as single images in a directory.

        :param configuration: Configuration object with parameters
        :param names: In case "video": name of the video file. In case "image": list of names for
                      all images.
        :param type: Either "video" or "image".
        :param convert_to_grayscale: If "True", convert frames to grayscale if they are RGB.
        :param progress_signal: Either None (no progress signalling), or a signal with the signature
                                (str, int) with the current activity (str) and the progress in
                                percent (int).
        :param buffer_original: If "True", read the original frame data only once, otherwise
                                read them again if required.
        :param buffer_monochrome: If "True", compute the monochrome image only once, otherwise
                                  compute it again if required. This may include re-reading the
                                  original image data.
        :param buffer_gaussian: If "True", compute the gaussian-blurred image only once, otherwise
                                compute it again if required. This may include re-reading the
                                original image data.
        :param buffer_laplacian: If "True", compute the "Laplacian of Gaussian" only once, otherwise
                                 compute it again if required. This may include re-reading the
                                 original image data.
        """

        self.configuration = configuration
        self.names = names
        self.progress_signal = progress_signal
        self.type = type
        self.convert_to_grayscale = convert_to_grayscale

        self.buffer_original = buffer_original
        self.buffer_monochrome = buffer_monochrome
        self.buffer_gaussian = buffer_gaussian
        self.buffer_laplacian = buffer_laplacian

        # In non-buffered mode, the index of the image just read/computed is stored for re-use.
        self.original_available = None
        self.original_available_index = -1
        self.monochrome_available = None
        self.monochrome_available_index = -1
        self.gaussian_available = None
        self.gaussian_available_index = -1
        self.laplacian_available = None
        self.laplacian_available_index = None

        # Compute the scaling value for Laplacian computation.
        self.alpha = 1. / 256.

        # Initialize and open the reader object.
        if self.type == 'image':
            self.reader = ImageReader()
        elif self.type == 'video':
            self.reader = VideoReader()
        else:
            raise TypeError("Image type " + self.type + " not supported")

        self.number, self.color, self.dt0, self.shape = self.reader.open(self.names,
                                                    convert_to_grayscale=self.convert_to_grayscale)

        # Set the depth value of all images to either 16 or 8 bits.
        if self.dt0 == 'uint16':
            self.depth = 16
        elif self.dt0 == 'uint8':
            self.depth = 8
        else:
            raise TypeError("Frame type " + str(self.dt0) + " not supported")

        # If the original frames are to be buffered, read them in one go. In this case, a progress
        # bar is displayed in the main GUI.
        if self.buffer_original:
            self.frames_original = []
            self.signal_step_size = max(int(self.number / 10), 1)
            for frame_index in range(self.number):
                # After every "signal_step_size"th frame, send a progress signal to the main GUI.
                if self.progress_signal is not None and frame_index % self.signal_step_size == 0:
                    self.progress_signal.emit("Read all frames",
                                              int((frame_index / self.number) * 100.))
                # Read the next frame.
                self.frames_original.append(self.reader.read_frame())

            self.reader.close()

        # If original frames are not buffered, initialize an empty frame list, so frames can be
        # read later in non-consecutive order.
        else:
            self.frames_original = [None for index in range(self.number)]

        # Initialize lists of monochrome frames (with and without Gaussian blur) and their
        # Laplacians.
        colors = ['red', 'green', 'blue', 'panchromatic']
        if self.configuration.frames_mono_channel in colors:
            self.color_index = colors.index(self.configuration.frames_mono_channel)
        else:
            raise ArgumentError("Invalid color selected for channel extraction")
        self.frames_monochrome = [None for index in range(self.number)]
        self.frames_monochrome_blurred = [None for index in range(self.number)]
        self.frames_monochrome_blurred_laplacian = [None for index in range(self.number)]
        self.used_alignment_points = None

    def frames(self, index):
        """
        Read or look up the original frame object with a given index.

        :param index: Frame index
        :return: Frame with index "index".
        """

        if not 0 <= index < self.number:
            raise ArgumentError("Frame index " + str(index) + " is out of bounds")
        # print ("Accessing frame " + str(index))

        # The original frames are buffered. Just return the frame.
        if self.buffer_original:
            return self.frames_original[index]

        # This frame has been cached. Just return it.
        if self.original_available_index == index:
            return self.original_available

        # The frame has not been stored for re-use, read it.
        else:
            if self.type == 'image':
                if self.convert_to_grayscale:
                    frame = misc.imread(self.names[index], mode='F')
                else:
                    frame = cvtColor(imread(self.names[index], -1), COLOR_BGR2RGB)
            else:
                frame = self.reader.read_frame(index)

            # Cache the frame just read.
            self.original_available = frame
            self.original_available_index = index

            # For the first frame read, set image metadata.
            if self.shape is None:
                self.shape = frame.shape
                # Monochrome images are stored as 2D arrays, color images as 3D.
                if len(self.shape) == 2:
                    self.color = False
                elif len(self.shape) == 3:
                    self.color = True
                else:
                    raise ShapeError("Image shape not supported")

                self.dt0 = frame.dtype
                # Set the depth value of all images to either 16 or 8 bits.
                if self.dt0 == 'uint16':
                    self.depth = 16
                elif self.dt0 == 'uint8':
                    self.depth = 8
                else:
                    raise TypeError("Frame type " + str(self.dt0) + " not supported")

            # For every other frame, check for consistency.
            else:
                if len(frame.shape) != len(self.shape):
                    raise ShapeError("Mixing grayscale and color images not supported")
                elif frame.shape != self.shape:
                    raise ShapeError("Images have different size")
                if frame.dtype != self.dt0:
                    raise TypeError("Images have different type")

            return frame

    def frames_mono(self, index):
        """
        Look up or compute the monochrome version of the frame object with a given index.

        :param index: Frame index
        :return: Monochrome frame with index "index".
        """

        if not 0 <= index < self.number:
            raise ArgumentError("Frame index " + str(index) + " is out of bounds")

        # print("Accessing frame monochrome " + str(index))
        # The monochrome frames are buffered, and this frame has been stored before. Just return
        # the frame.
        if self.frames_monochrome[index] is not None:
            return self.frames_monochrome[index]

        # If the monochrome frame is cached, just return it.
        if self.monochrome_available_index == index:
            return self.monochrome_available

        # The frame has not been stored for re-use, compute it.
        else:

            # Get the original frame. If it is not cached, this involves I/O.
            frame_original = self.frames(index)

            # If frames are in color mode produce a B/W version.
            if self.color:
                if self.color_index == 3:
                    frame_mono = cvtColor(frame_original, COLOR_BGR2GRAY)
                else:
                    frame_mono = frame_original[:, :, self.color_index]
            # Frames are in B/W mode already
            else:
                frame_mono = frame_original

            # If the monochrome frames are buffered, store it at the current index.
            if self.buffer_monochrome:
                self.frames_monochrome[index] = frame_mono

            # If frames are not buffered, cache the current frame.
            else:
                self.monochrome_available_index = index
                self.monochrome_available = frame_mono

            return frame_mono

    def frames_mono_blurred(self, index):
        """
        Look up a Gaussian-blurred frame object with a given index.

        :param index: Frame index
        :return: Gaussian-blurred frame with index "index".
        """

        if not 0 <= index < self.number:
            raise ArgumentError("Frame index " + str(index) + " is out of bounds")

        # print("Accessing frame with Gaussian blur " + str(index))
        # The blurred frames are buffered, and this frame has been stored before. Just return
        # the frame.
        if self.frames_monochrome_blurred[index] is not None:
            return self.frames_monochrome_blurred[index]

        # If the blurred frame is cached, just return it.
        if self.gaussian_available_index == index:
            return self.gaussian_available

        # The frame has not been stored for re-use, compute it.
        else:

            # Get the monochrome frame. If it is not cached, this involves I/O.
            frame_mono = self.frames_mono(index)

            # If the mono image is 8bit, interpolate it to 16bit.
            if frame_mono.dtype == np.uint8:
                frame_mono = frame_mono.astype(np.uint16) * 256

            # Compute a version of the frame with Gaussian blur added.
            frame_monochrome_blurred = GaussianBlur(frame_mono,
                                                    (self.configuration.frames_gauss_width,
                                                     self.configuration.frames_gauss_width), 0)

            # If the blurred frames are buffered, store the current frame at the current index.
            if self.buffer_gaussian:
                self.frames_monochrome_blurred[index] = frame_monochrome_blurred

            # If frames are not buffered, cache the current frame.
            else:
                self.gaussian_available_index = index
                self.gaussian_available = frame_monochrome_blurred

            return frame_monochrome_blurred

    def frames_mono_blurred_laplacian(self, index):
        """
        Look up a Laplacian-of-Gaussian of a frame object with a given index.

        :param index: Frame index
        :return: LoG of a frame with index "index".
        """

        if not 0 <= index < self.number:
            raise ArgumentError("Frame index " + str(index) + " is out of bounds")

        # print("Accessing LoG number " + str(index))
        # The LoG frames are buffered, and this frame has been stored before. Just return the frame.
        if self.frames_monochrome_blurred_laplacian[index] is not None:
            return self.frames_monochrome_blurred_laplacian[index]

        # If the blurred frame is cached, just return it.
        if self.laplacian_available_index == index:
            return self.laplacian_available

        # The frame has not been stored for re-use, compute it.
        else:

            # Get the monochrome frame. If it is not cached, this involves I/O.
            frame_monochrome_blurred = self.frames_mono_blurred(index)

            # Compute a version of the frame with Gaussian blur added.
            frame_monochrome_laplacian = convertScaleAbs(Laplacian(
                frame_monochrome_blurred[::self.configuration.align_frames_sampling_stride,
                ::self.configuration.align_frames_sampling_stride], CV_32F),
                alpha=self.alpha)

            # If the blurred frames are buffered, store the current frame at the current index.
            if self.buffer_laplacian:
                self.frames_monochrome_blurred_laplacian[index] = frame_monochrome_laplacian

            # If frames are not buffered, cache the current frame.
            else:
                self.laplacian_available_index = index
                self.laplacian_available = frame_monochrome_laplacian

            return frame_monochrome_laplacian

    def reset_alignment_point_lists(self):
        """
        Every frame keeps a list with the alignment points for which this frame is among the
        sharpest ones (so it is used in stacking). Reset this list for all frames.

        :return: -
        """

        # For every frame initialize the list with used alignment points.
        self.used_alignment_points = [[] for index in range(self.number)]

    @staticmethod
    def save_image(filename, image, color=False, avoid_overwriting=True):
        """
        Save an image to a file.

        :param filename: Name of the file where the image is to be written
        :param image: ndarray object containing the image data
        :param color: If True, a three channel RGB image is to be saved. Otherwise, monochrome.
        :param avoid_overwriting: If True, append a string to the input name if necessary so that
                                  it does not match any existing file. If False, overwrite
                                  an existing file.
        :return: -
        """

        if avoid_overwriting:
            # If a file or directory with the given name already exists, append the word "_file".
            if Path(filename).is_dir():
                while True:
                    filename += '_file'
                    if not Path(filename).exists():
                        break
                filename += '.jpg'
            # If it is a file, try to append "_copy.tiff" to its basename. If it still exists, repeat.
            elif Path(filename).is_file():
                suffix = Path(filename).suffix
                while True:
                    p = Path(filename)
                    filename = Path.joinpath(p.parents[0], p.stem + '_copy' + suffix)
                    if not Path(filename).exists():
                        break
            else:
                # If the file name is new and has no suffix, add ".tiff".
                suffix = Path(filename).suffix
                if not suffix:
                    filename += '.tiff'

        # Don't care if a file with the given name exists. Overwrite it if necessary.
        elif path.exists(filename):
            remove(filename)

        # Write the image to the file. Before writing, convert the internal RGB representation into
        # the BGR representation assumed by OpenCV.
        if color:
            imwrite(str(filename), cvtColor(image, COLOR_RGB2BGR))
        else:
            imwrite(str(filename), image)


def access_pattern(frames_object, average_frame_percent):
    """
    Simulate the access pattern of PSS to frame data, without any other activity in between. Return
    the overall time.

    :param frames_object: Frames object to access frames.
    :param average_frame_percent: Percentage of frames for average image computation.
    :return: Total time in seconds.
    """

    number = frames.number
    average_frame_number = max(
        ceil(number * average_frame_percent / 100.), 1)
    start = time()

    for index in range(number):
        frames_object.frames_mono_blurred_laplacian(index)

    frames_object.frames_mono_blurred(number - 1)
    frames_object.frames_mono_blurred(number - 1)

    for index in range(number):
        frames_object.frames_mono_blurred(index)

    for index in range(average_frame_number):
        frames_object.frames_mono(index)

    for index in range(number):
        frames_object.frames_mono_blurred_laplacian(index)

    for index in range(number):
        frames_object.frames(index)
        frames_object.frames_mono_blurred(index)

    return time() - start


if __name__ == "__main__":

    # Images can either be extracted from a video file or a batch of single photographs. Select
    # the example for the test run.
    type = 'image'
    version = 'frames'
    buffering_level = 2

    if type == 'image':
        # names = glob('Images/2012_*.tif')
        # names = glob('D:\SW-Development\Python\PlanetarySystemStacker\Examples\Moon_2011-04-10\South\*.TIF')
        names = glob(
            'D:\SW-Development\Python\PlanetarySystemStacker\Examples\Moon_2019-01-20\Images\*.TIF')
    else:
        names = 'Videos/another_short_video.avi'
        # names = 'Videos/Moon_Tile-024_043939.avi'

    # Get configuration parameters.
    configuration = Configuration()

    # Decide on the objects to be buffered, depending on configuration parameter.
    buffer_original = False
    buffer_monochrome = False
    buffer_gaussian = False
    buffer_laplacian = False

    if buffering_level > 0:
        buffer_laplacian = True
    if buffering_level > 1:
        buffer_gaussian = True
    if buffering_level > 2:
        buffer_original = True
    if buffering_level > 3:
        buffer_monochrome = True

    start = time()
    if version == 'frames':
        try:
            frames = Frames(configuration, names, type=type, convert_to_grayscale=False,
                            buffer_original=buffer_original, buffer_monochrome=buffer_monochrome,
                            buffer_gaussian=buffer_gaussian, buffer_laplacian=buffer_laplacian)
        except Exception as e:
            print("Error: " + e.message)
            exit()
        frames_mono_3 = frames.frames_mono(3)
        frames_mono_blurred_4 = frames.frames_mono_blurred(4)
        frames_mono_blurred_laplacian_1 = frames.frames_mono_blurred_laplacian(1)
    else:
        try:
            frames = FramesOld(configuration, names, type=type, convert_to_grayscale=False)
            frames.add_monochrome(configuration.frames_mono_channel)
        except Exception as e:
            print("Error: " + e.message)
            exit()
    initialization_time = time() - start

    print("Number of images read: " + str(frames.number))
    print("Image shape: " + str(frames.shape))

    total_access_time = access_pattern(frames, configuration.align_frames_average_frame_percent)

    print("\nInitialization time: {0:7.3f}, frame accesses and variant computations: {1:7.3f},"
          " total: {2:7.3f} (seconds)".format(initialization_time, total_access_time,
                                              initialization_time + total_access_time))
