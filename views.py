#!/usr/bin/env python
# -*- coding: utf-8 -*-
# FreqShow application views.
# These contain the majority of the application business logic.
# Author: Tony DiCola (tony@tonydicola.com)
#
# The MIT License (MIT)
#
# Copyright (c) 2014 Adafruit Industries
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import math
import sys

import numpy as np
import pygame

import freqshow
import ui
import controller

import time

import requests
import json
from urlparse import urlparse
import urllib

# Color and gradient interpolation functions used by waterfall spectrogram.


def lerp(x, x0, x1, y0, y1):
    """Linear interpolation of value y given min and max y values (y0 and y1),
    min and max x values (x0 and x1), and x value.
    """
    return y0 + (y1 - y0) * ((x - x0) / (x1 - x0))


def rgb_lerp(x, x0, x1, c0, c1):
    """Linear interpolation of RGB color tuple c0 and c1."""
    return (math.floor(lerp(x, x0, x1, float(c0[0]), float(c1[0]))),
            math.floor(lerp(x, x0, x1, float(c0[1]), float(c1[1]))),
            math.floor(lerp(x, x0, x1, float(c0[2]), float(c1[2]))))


def gradient_func(colors):
    """Build a waterfall color function from a list of RGB color tuples.  The
    returned function will take a numeric value from 0 to 1 and return a color
    interpolated across the gradient of provided RGB colors.
    """
    grad_width = 1.0 / (len(colors) - 1.0)

    def _fun(value):
        if value <= 0.0:
            return colors[0]
        elif value >= 1.0:
            return colors[-1]
        else:
            pos = int(value / grad_width)
            c0 = colors[pos]
            c1 = colors[pos + 1]
            x = (value % grad_width) / grad_width
            return rgb_lerp(x, 0.0, 1.0, c0, c1)
    return _fun


def clamp(x, x0, x1):
    """Clamp a provided value to be between x0 and x1 (inclusive).  If value is
    outside the range it will be truncated to the min/max value which is closest.
    """
    if x > x1:
        return x1
    elif x < x0:
        return x0
    else:
        return x


class ViewBase(object):
    """Base class for simple UI view which represents all the elements drawn
    on the screen.  Subclasses should override the render, and click functions.
    """

    def render(self, screen):
        pass

    def click(self, location):
        pass


class MessageDialog(ViewBase):
    """Dialog which displays a message in the center of the screen with an OK
    and optional cancel button.
    """

    def __init__(self, model, text, accept, cancel=None):
        self.accept = accept
        self.cancel = cancel
        self.buttons = ui.ButtonGrid(model.width, model.height, 4, 5)
        self.buttons.add(3, 4, 'OK', click=self.accept_click,
                         bg_color=freqshow.ACCEPT_BG)
        if cancel is not None:
            self.buttons.add(0, 4, 'CANCEL', click=self.cancel_click,
                             bg_color=freqshow.CANCEL_BG)
        self.label = ui.render_text(text, size=freqshow.NUM_FONT,
                                    fg=freqshow.BUTTON_FG, bg=freqshow.MAIN_BG)
        self.label_rect = ui.align(self.label.get_rect(),
                                   (0, 0, model.width, model.height))

    def render(self, screen):
        # Draw background, buttons, and text.
        screen.fill(freqshow.MAIN_BG)
        self.buttons.render(screen)
        screen.blit(self.label, self.label_rect)

    def click(self, location):
        self.buttons.click(location)

    def accept_click(self, button):
        self.accept()

    def cancel_click(self, button):
        self.cancel()


class NumberDialog(ViewBase):
    """Dialog which asks the user to enter a numeric value."""

    def __init__(self, model, label_text, unit_text, initial='0', accept=None,
                 cancel=None, has_auto=False, allow_negative=False):
        """Create number dialog for provided model and with given label and unit
        text.  Can provide an optional initial value (default to 0), an accept
        callback function which is called when the user accepts the dialog (and
        the chosen value will be sent as a single parameter), a cancel callback
        which is called when the user cancels, and a has_auto boolean if an
        'AUTO' option should be given in addition to numbers.
        """
        self.value = str(initial)
        self.unit_text = unit_text
        self.model = model
        self.accept = accept
        self.cancel = cancel
        # Initialize button grid.
        self.buttons = ui.ButtonGrid(model.width, model.height, 4, 5)
        self.buttons.add(0, 1, '1', font_size=freqshow.NUM_FONT,
                         click=self.number_click)
        self.buttons.add(1, 1, '2', font_size=freqshow.NUM_FONT,
                         click=self.number_click)
        self.buttons.add(2, 1, '3', font_size=freqshow.NUM_FONT,
                         click=self.number_click)
        self.buttons.add(0, 2, '4', font_size=freqshow.NUM_FONT,
                         click=self.number_click)
        self.buttons.add(1, 2, '5', font_size=freqshow.NUM_FONT,
                         click=self.number_click)
        self.buttons.add(2, 2, '6', font_size=freqshow.NUM_FONT,
                         click=self.number_click)
        self.buttons.add(0, 3, '7', font_size=freqshow.NUM_FONT,
                         click=self.number_click)
        self.buttons.add(1, 3, '8', font_size=freqshow.NUM_FONT,
                         click=self.number_click)
        self.buttons.add(2, 3, '9', font_size=freqshow.NUM_FONT,
                         click=self.number_click)
        self.buttons.add(1, 4, '0', font_size=freqshow.NUM_FONT,
                         click=self.number_click)
        self.buttons.add(2, 4, '.', font_size=freqshow.NUM_FONT,
                         click=self.decimal_click)
        self.buttons.add(0, 4, 'DELETE', click=self.delete_click)
        if not allow_negative:
            # Render a clear button if only positive values are allowed.
            self.buttons.add(3, 1, 'CLEAR', click=self.clear_click)
        else:
            # Render a +/- toggle if negative values are allowed.
            self.buttons.add(3, 1, '+/-', click=self.posneg_click)
        self.buttons.add(3, 3, 'CANCEL', click=self.cancel_click,
                         bg_color=freqshow.CANCEL_BG)
        self.buttons.add(3, 4, 'ACCEPT', click=self.accept_click,
                         bg_color=freqshow.ACCEPT_BG)
        if has_auto:
            self.buttons.add(3, 2, 'AUTO', click=self.auto_click)
        # Build label text for faster rendering.
        self.input_rect = (0, 0, self.model.width, self.buttons.row_size)
        self.label = ui.render_text(label_text, size=freqshow.MAIN_FONT,
                                    fg=freqshow.INPUT_FG, bg=freqshow.INPUT_BG)
        self.label_pos = ui.align(self.label.get_rect(), self.input_rect,
                                  horizontal=ui.ALIGN_LEFT, hpad=10)

    def render(self, screen):
        # Clear view and draw background.
        screen.fill(freqshow.MAIN_BG)
        # Draw input background at top of screen.
        screen.fill(freqshow.INPUT_BG, self.input_rect)
        # Render label and value text.
        screen.blit(self.label, self.label_pos)
        value_label = ui.render_text('{0} {1}'.format(self.value, self.unit_text),
                                     size=freqshow.NUM_FONT, fg=freqshow.INPUT_FG, bg=freqshow.INPUT_BG)
        screen.blit(value_label, ui.align(value_label.get_rect(), self.input_rect,
                                          horizontal=ui.ALIGN_RIGHT, hpad=-10))
        # Render buttons.
        self.buttons.render(screen)

    def click(self, location):
        self.buttons.click(location)

    # Button click handlers follow below.
    def auto_click(self, button):
        self.value = 'AUTO'

    def clear_click(self, button):
        self.value = '0'

    def delete_click(self, button):
        if self.value == 'AUTO':
            # Ignore delete in auto gain mode.
            return
        elif len(self.value) > 1:
            # Delete last character.
            self.value = self.value[:-1]
        else:
            # Set value to 0 if only 1 character.
            self.value = '0'

    def cancel_click(self, button):
        if self.cancel is not None:
            self.cancel()

    def accept_click(self, button):
        if self.accept is not None:
            self.accept(self.value)

    def decimal_click(self, button):
        if self.value == 'AUTO':
            # If in auto gain, assume user wants numeric gain with decimal.
            self.value = '0.'
        elif self.value.find('.') == -1:
            # Only add decimal if none is present.
            self.value += '.'

    def number_click(self, button):
        if self.value == '0' or self.value == 'AUTO':
            # Replace value with number if no value or auto gain is set.
            self.value = button.text
        else:
            # Add number to end of value.
            self.value += button.text

    def posneg_click(self, button):
        if self.value == 'AUTO':
            # Do nothing if value is auto.
            return
        else:
            if self.value[0] == '-':
                # Swap negative to positive by removing leading minus.
                self.value = self.value[1:]
            else:
                # Swap positive to negative by adding leading minus.
                self.value = '-' + self.value

################################################TRACK##############################################################


class PuaseDialog(ViewBase):
    """Dialog which asks the user to enter a numeric value."""

    def __init__(self, model, label_text, unit_text, initial='0', accept=None,
                 cancel=None, has_auto=False, allow_negative=False):
        """Create number dialog for provided model and with given label and unit
        text.  Can provide an optional initial value (default to 0), an accept
        callback function which is called when the user accepts the dialog (and
        the chosen value will be sent as a single parameter), a cancel callback
        which is called when the user cancels, and a has_auto boolean if an
        'AUTO' option should be given in addition to numbers.
        """
        self.value = str(initial)
        self.unit_text = unit_text
        self.model = model
        self.accept = accept
        self.cancel = cancel
        # Initialize button grid.
        self.buttons = ui.ButtonGrid(model.width, model.height, 4, 5)
        self.buttons.add(0, 1, 'ENABLE', font_size=freqshow.NUM_FONT,
                         click=self.enable_click, colspan=2)
        self.buttons.add(2, 1, 'DISABLE', font_size=freqshow.NUM_FONT,
                         click=self.disable_click, colspan=2)

        self.buttons.add(0, 4, 'CANCEL', click=self.cancel_click,
                         bg_color=freqshow.CANCEL_BG)
        self.buttons.add(3, 4, 'ACCEPT', click=self.accept_click,
                         bg_color=freqshow.ACCEPT_BG)

        # Build label text for faster rendering.
        self.input_rect = (0, 0, self.model.width, self.buttons.row_size)
        self.label = ui.render_text(label_text, size=freqshow.MAIN_FONT,
                                    fg=freqshow.INPUT_FG, bg=freqshow.INPUT_BG)
        self.label_pos = ui.align(self.label.get_rect(), self.input_rect,
                                  horizontal=ui.ALIGN_LEFT, hpad=10)

    def render(self, screen):
        # Clear view and draw background.
        screen.fill(freqshow.MAIN_BG)
        # Draw input background at top of screen.
        screen.fill(freqshow.INPUT_BG, self.input_rect)
        # Render label and value text.
        screen.blit(self.label, self.label_pos)
        value_label = ui.render_text('{0} {1}'.format(self.value, self.unit_text),
                                     size=freqshow.NUM_FONT, fg=freqshow.INPUT_FG, bg=freqshow.INPUT_BG)
        screen.blit(value_label, ui.align(value_label.get_rect(), self.input_rect,
                                          horizontal=ui.ALIGN_RIGHT, hpad=-10))
        # Render buttons.
        self.buttons.render(screen)

    def enable_click(self, button):
        self.value = 'ENABLE'

    def disable_click(self, button):
        self.value = 'DISABLE'

    def click(self, location):
        self.buttons.click(location)

    # Button click handlers follow below.

    def cancel_click(self, button):
        if self.cancel is not None:
            self.cancel()

    def accept_click(self, button):
        if self.accept is not None:
            self.accept(self.value)


##############################################################################################################

class SettingsList(ViewBase):
    """Setting list view. Allows user to modify some model configuration."""

    def __init__(self, model, controller):
        # self.sweep_start_enabled = False
        # self.sweep_stop_enabled = False
        self.model = model
        self.controller = controller
        # Create button labels with current model values.
        centerfreq_text = 'CENTER FREQ: {0:0.2f} MHz'.format(
            model.get_center_freq())
        samplerate_text = 'SPAN: {0:0.2f} MHz'.format(model.get_sample_rate())
        gain_text = 'GAIN: {0} dBm'.format(model.get_gain())
        min_text = 'MIN: {0} dBm'.format(model.get_min_string())
        max_text = 'MAX: {0} dBm'.format(model.get_max_string())
        start_text = 'START: {0} MHz'.format(model.get_start_string())
        stop_text = 'STOP: {0} MHz'.format(model.get_stop_string())
        step_text = 'STEP: {0} MHz'.format(model.get_step_string())
        puase_text = 'TRACK: {0}'.format(model.get_puase_string())
        # Create buttons.
        self.buttons = ui.ButtonGrid(model.width, model.height, 6, 7)
        self.buttons.add(0, 0, centerfreq_text, colspan=6,
                         click=self.centerfreq_click)
        self.buttons.add(0, 1, samplerate_text, colspan=6,
                         click=self.sample_click)
        self.buttons.add(0, 2, gain_text,       colspan=6,
                         click=self.gain_click)
        self.buttons.add(0, 3, min_text,        colspan=3,
                         click=self.min_click)
        self.buttons.add(3, 3, max_text,        colspan=3,
                         click=self.max_click)
        # self.buttons.add(0, 4, start_text,        colspan=3, click=self.start_click)
        # self.buttons.add(3, 4, step_text,        colspan=3, click=self.step_click)
        # self.buttons.add(0, 5, stop_text,        colspan=3, click=self.stop_click)
        # self.buttons.add(3, 5, puase_text,        colspan=3, click=self.puase_click)
        self.buttons.add(0, 6, 'BACK', click=self.controller.change_to_main)
        self.buttons.add(5, 6, 'Page2', click=self.page2_click)
        self.puase_disable = True

    def render(self, screen):
        # Clear view and render buttons.
        screen.fill(freqshow.MAIN_BG)
        self.buttons.render(screen)

    def click(self, location):
        self.buttons.click(location)

    # Button click handlers follow below.
    def centerfreq_click(self, button):
        self.controller.number_dialog('FREQUENCY:', 'MHz',
                                      initial='{0:0.2f}'.format(
                                          self.model.get_center_freq()),
                                      accept=self.centerfreq_accept)

    def centerfreq_accept(self, value):
        self.model.set_center_freq(float(value))
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def sample_click(self, button):
        self.controller.number_dialog('SAMPLE RATE:', 'MHz',
                                      initial='{0:0.2f}'.format(
                                          self.model.get_sample_rate()),
                                      accept=self.sample_accept)

    def sample_accept(self, value):
        self.model.set_sample_rate(float(value))
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def gain_click(self, button):
        self.controller.number_dialog('GAIN:', 'dBm',
                                      initial=self.model.get_gain(), accept=self.gain_accept,
                                      has_auto=True)

    def gain_accept(self, value):
        self.model.set_gain(value)
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def min_click(self, button):
        self.controller.number_dialog('MIN:', 'dBm',
                                      initial=self.model.get_min_string(), accept=self.min_accept,
                                      has_auto=True, allow_negative=True)

    def min_accept(self, value):
        self.model.set_min_intensity(value)
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def max_click(self, button):
        self.controller.number_dialog('MAX:', 'dBm',
                                      initial=self.model.get_max_string(), accept=self.max_accept,
                                      has_auto=True, allow_negative=True)

    def max_accept(self, value):
        self.model.set_max_intensity(value)
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def start_click(self, button):
        self.controller.number_dialog('START:', 'MHz',
                                      initial=self.model.get_start_string(), accept=self.start_accept)

    def start_accept(self, value):
        self.model.set_start_intensity(value)
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def stop_click(self, button):
        self.controller.number_dialog('STOP:', 'MHz',
                                      initial=self.model.get_stop_string(), accept=self.stop_accept)

    def stop_accept(self, value):
        self.model.set_stop_intensity(value)
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def step_click(self, button):
        self.controller.number_dialog('STEP:', 'MHz',
                                      initial=self.model.get_step_string(), accept=self.step_accept)

    def step_accept(self, value):
        self.model.set_step_intensity(value)
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def puase_click(self, button):
        self.controller.puase_dialog('TRACK:', 'State',
                                     initial=self.model.get_puase_string(), accept=self.puase_accept)

    def puase_accept(self, value):
        self.model.set_puase_intensity(value)
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def page2_click(self, button):
        self.controller.change_to_page2()

#################################################PAGE 2########################################################


class SettingsList2(ViewBase):
    """Setting list view. Allows user to modify some model configuration."""

    def __init__(self, model, controller):
        # self.sweep_start_enabled = False
        # self.sweep_stop_enabled = False
        self.model = model
        self.controller = controller
        # Create button labels with current model values.
        centerfreq_text = 'CENTER FREQ: {0:0.2f} MHz'.format(
            model.get_center_freq())
        samplerate_text = 'SPAN: {0:0.2f} MHz'.format(model.get_sample_rate())
        gain_text = 'GAIN: {0} dBm'.format(model.get_gain())
        min_text = 'MIN: {0} dBm'.format(model.get_min_string())
        max_text = 'MAX: {0} dBm'.format(model.get_max_string())
        start_text = 'START: {0} MHz'.format(model.get_start_string())
        stop_text = 'STOP: {0} MHz'.format(model.get_stop_string())
        step_text = 'STEP: {0} MHz'.format(model.get_step_string())
        puase_text = 'TRACK: {0}'.format(model.get_puase_string())
        threshold_text = 'THRESHOLD: {0}'.format(model.get_threshold_string())
        # Create buttons.
        self.buttons = ui.ButtonGrid(model.width, model.height, 6, 7)
        # self.buttons.add(0, 0, centerfreq_text, colspan=6, click=self.centerfreq_click)
        # self.buttons.add(0, 1, samplerate_text, colspan=6, click=self.sample_click)
        # self.buttons.add(0, 2, gain_text,       colspan=6, click=self.gain_click)
        # self.buttons.add(0, 3, min_text,        colspan=3, click=self.min_click)
        # self.buttons.add(3, 3, max_text,        colspan=3, click=self.max_click)
        self.buttons.add(0, 0, start_text,        colspan=3,
                         click=self.start_click)
        self.buttons.add(0, 1, step_text,        colspan=3,
                         click=self.step_click)
        self.buttons.add(3, 0, stop_text,        colspan=3,
                         click=self.stop_click)
        self.buttons.add(0, 2, threshold_text,
                         colspan=3, click=self.threshold_click)
        self.buttons.add(3, 2, puase_text,        colspan=3,
                         click=self.puase_click)
        self.buttons.add(0, 6, 'BACK', click=self.controller.change_to_main)
        self.buttons.add(5, 6, 'Page1', click=self.page1_click)
        self.puase_disable = True

    def render(self, screen):
        # Clear view and render buttons.
        screen.fill(freqshow.MAIN_BG)
        self.buttons.render(screen)

    def click(self, location):
        self.buttons.click(location)

    # Button click handlers follow below.
    def centerfreq_click(self, button):
        self.controller.number_dialog('FREQUENCY:', 'MHz',
                                      initial='{0:0.2f}'.format(
                                          self.model.get_center_freq()),
                                      accept=self.centerfreq_accept)

    def centerfreq_accept(self, value):
        self.model.set_center_freq(float(value))
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def sample_click(self, button):
        self.controller.number_dialog('SAMPLE RATE:', 'MHz',
                                      initial='{0:0.2f}'.format(
                                          self.model.get_sample_rate()),
                                      accept=self.sample_accept)

    def sample_accept(self, value):
        self.model.set_sample_rate(float(value))
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def gain_click(self, button):
        self.controller.number_dialog('GAIN:', 'dBm',
                                      initial=self.model.get_gain(), accept=self.gain_accept,
                                      has_auto=True)

    def gain_accept(self, value):
        self.model.set_gain(value)
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def min_click(self, button):
        self.controller.number_dialog('MIN:', 'dBm',
                                      initial=self.model.get_min_string(), accept=self.min_accept,
                                      has_auto=True, allow_negative=True)

    def min_accept(self, value):
        self.model.set_min_intensity(value)
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def max_click(self, button):
        self.controller.number_dialog('MAX:', 'dBm',
                                      initial=self.model.get_max_string(), accept=self.max_accept,
                                      has_auto=True, allow_negative=True)

    def max_accept(self, value):
        self.model.set_max_intensity(value)
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def start_click(self, button):
        self.controller.number_dialog('START:', 'MHz',
                                      initial=self.model.get_start_string(), accept=self.start_accept)

    def start_accept(self, value):
        self.model.set_start_intensity(value)
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def stop_click(self, button):
        self.controller.number_dialog('STOP:', 'MHz',
                                      initial=self.model.get_stop_string(), accept=self.stop_accept)

    def stop_accept(self, value):
        self.model.set_stop_intensity(value)
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def step_click(self, button):
        self.controller.number_dialog('STEP:', 'MHz',
                                      initial=self.model.get_step_string(), accept=self.step_accept)

    def step_accept(self, value):
        self.model.set_step_intensity(value)
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def puase_click(self, button):
        self.controller.puase_dialog('TRACK:', 'State',
                                     initial=self.model.get_puase_string(), accept=self.puase_accept)

    def puase_accept(self, value):
        self.model.set_puase_intensity(value)
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def threshold_click(self, button):
        self.controller.number_dialog('THRESHOLD:', 'dBm',
                                      initial=self.model.get_threshold_string(), accept=self.threshold_accept,
                                      has_auto=True, allow_negative=True)

    def threshold_accept(self, value):
        self.model.set_threshold_intensity(value)
        self.controller.waterfall.clear_waterfall()
        self.controller.change_to_settings()

    def page1_click(self, button):
        self.controller.change_to_page1()


###############################################################################################################

class SpectrogramBase(ViewBase):
    """Base class for a spectrogram view."""

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.buttons = ui.ButtonGrid(model.width, model.height, 10, 8)
        self.buttons.add(
            1, 0, 'SET', click=self.controller.change_to_settings, colspan=2)
        # self.buttons.add(3, 0, 'STOP', click=self.controller.change_to_justinstant, colspan=2)
        self.buttons.add(3, 0, 'SWEEP', click=self.controller.change_to_sweep, colspan=4)
        self.buttons.add(7, 0, 'QUIT', click=self.quit_click,
                         bg_color=freqshow.CANCEL_BG, colspan=2)
        self.buttons.add(0, 0, '<', click=self.previous_click)
        self.buttons.add(9, 0, '>', click=self.next_click)
        self.overlay_enabled = True
        self.sweep_enabled = True
        stop_text = '{0}'.format(model.get_stop_string())

    def render_spectrogram(self, screen):
        """Subclass should implement spectorgram rendering in the provided
        surface.
        """
        raise NotImplementedError

    def render_hash(self, screen, x, size=5, padding=2):
        """Draw a hash mark (triangle) on the bottom row at the specified x
        position.
        """
        y = self.model.height - self.buttons.row_size + padding
        pygame.draw.lines(screen, freqshow.BUTTON_FG, False,
                          [(x, y), (x - size, y + size), (x + size, y + size), (x, y), (x, y + 2 * size)])

    def render(self, screen):
        # Clear screen.
        screen.fill(freqshow.MAIN_BG)
        if self.overlay_enabled:
            # Draw shrunken spectrogram with overlaid buttons and axes values.
            spect_rect = (0, self.buttons.row_size, self.model.width,
                          self.model.height - 2 * self.buttons.row_size)
            self.render_spectrogram(screen.subsurface(spect_rect))
            # Draw hash marks.
            self.render_hash(screen, 0)
            self.render_hash(screen, self.model.width / 2)
            self.render_hash(screen, self.model.width - 1)
            # Draw frequencies in bottom row.
            bottom_row = (0, self.model.height - self.buttons.row_size,
                          self.model.width, self.buttons.row_size)
            freq = self.model.get_center_freq()
            bandwidth = self.model.get_sample_rate()
            # Render minimum frequency on left.
            label = ui.render_text('{0:0.2f} Mhz'.format(freq - bandwidth / 2.0),
                                   size=freqshow.MAIN_FONT)
            screen.blit(label, ui.align(label.get_rect(), bottom_row,
                                        horizontal=ui.ALIGN_LEFT))
            # Render center frequency in center.
            label = ui.render_text('{0:0.2f} Mhz'.format(freq),
                                   size=freqshow.MAIN_FONT)
            screen.blit(label, ui.align(label.get_rect(), bottom_row,
                                        horizontal=ui.ALIGN_CENTER))
            # Render maximum frequency on right.
            label = ui.render_text('{0:0.2f} Mhz'.format(freq + bandwidth / 2.0),
                                   size=freqshow.MAIN_FONT)
            screen.blit(label, ui.align(label.get_rect(), bottom_row,
                                        horizontal=ui.ALIGN_RIGHT))
            # Render min intensity in bottom left.
            label = ui.render_text('{0:0.0f} dBm'.format(self.model.min_intensity),
                                   size=freqshow.MAIN_FONT)
            screen.blit(label, ui.align(label.get_rect(), spect_rect,
                                        horizontal=ui.ALIGN_LEFT, vertical=ui.ALIGN_BOTTOM))
            # Render max intensity in top left.
            label = ui.render_text('{0:0.0f} dBm'.format(self.model.max_intensity),
                                   size=freqshow.MAIN_FONT)
            screen.blit(label, ui.align(label.get_rect(), spect_rect,
                                        horizontal=ui.ALIGN_LEFT, vertical=ui.ALIGN_TOP))

            # Render max intensity track.
            # ymax = ymax/320
            # xmax = xmax/480
            label = ui.render_text('{0:0.0f} dBm'.format(ymax2),
                                   size=freqshow.MAIN_FONT)
            screen.blit(label, ui.align(label.get_rect(), spect_rect,
                                        horizontal=xmax_label * ui.ALIGN_RIGHT, vertical=0.5 * ui.ALIGN_BOTTOM))

            # Draw the buttons.
            self.buttons.render(screen)
        else:
            # Draw fullscreen spectrogram.
            self.render_spectrogram(screen)

    def click(self, location):
        mx, my = location
        if my > 2 * self.buttons.row_size and my < 7 * self.buttons.row_size:
            # Handle click on spectrogram.
            self.overlay_enabled = not self.overlay_enabled
        else:
            # Handle click on buttons.
            self.buttons.click(location)

    def quit_click(self, button):
        self.controller.message_dialog('QUIT: Are you sure?',
                                       accept=self.quit_accept)

    def quit_accept(self):
        sys.exit(0)

    def next_click(self, button):
        self.model.set_center_freq(
            self.model.get_center_freq() + self.model.get_sample_rate())

    def previous_click(self, button):
        self.model.set_center_freq(
            self.model.get_center_freq() - self.model.get_sample_rate())

    # def sw_click(self, button):
        # self.sweep_enabled = not self.sweep_enabled


class WaterfallSpectrogram(SpectrogramBase):
    """Scrolling waterfall plot of spectrogram data."""

    def __init__(self, model, controller):
        super(WaterfallSpectrogram, self).__init__(model, controller)
        self.color_func = gradient_func(freqshow.WATERFALL_GRAD)
        self.waterfall = pygame.Surface((model.width, model.height))

    def clear_waterfall(self):
        self.waterfall.fill(freqshow.MAIN_BG)

    def render_spectrogram(self, screen):
        # Grab spectrogram data.
        freqs = self.model.get_data()
        # Scroll up the waterfall display.
        self.waterfall.scroll(0, -1)
        # Scale the FFT values to the range 0 to 1.
        freqs = (freqs - self.model.min_intensity) / self.model.range
        # Convert scaled values to pixels drawn at the bottom of the display.
        x, y, width, height = screen.get_rect()
        wx, wy, wwidth, wheight = self.waterfall.get_rect()
        offset = wheight - height
        # Draw FFT values mapped through the gradient function to a color.
        self.waterfall.lock()
        for i in range(width):
            power = clamp(freqs[i], 0.0, 1.0)
            self.waterfall.set_at((i, wheight - 1), self.color_func(power))
        self.waterfall.unlock()
        screen.blit(self.waterfall, (0, 0), area=(0, offset, width, height))

class SweepSpectrogram(SpectrogramBase):
    """Instantaneous point in time line plot of the spectrogram."""

    def __init__(self, model, controller):
        super(SweepSpectrogram, self).__init__(model, controller)

    def render_spectrogram(self, screen):
        sw_stop = self.model.get_stop_sweep()
        sw_step = self.model.get_step_sweep()
        print('sweep render')
        if self.model.get_center_freq() < sw_stop:
            # Grab spectrogram data.
            freqs = self.model.get_data()
            # Scale frequency values to fit on the screen based on the min and max
            # intensity values.
            x, y, width, height = screen.get_rect()
            freqs2 = freqs
            freqs3 = freqs
            freqs4 = freqs
            freqs = height - np.floor(((freqs - self.model.min_intensity) / self.model.range) * height)
            # Render frequency graph.
            screen.fill(freqshow.MAIN_BG)
            # Draw line segments to join each FFT result bin.
            ylast = freqs[0]
            ymax = 320
            for i in range(1, width):
                y = freqs[i]
                pygame.draw.line(screen, freqshow.INSTANT_LINE,(i - 1, ylast), (i, y))
                ylast = y
                if i > 0:
                    if freqs[i] < ymax:
                        i_r = i + 24
                        i_l = i - 24
                        ymax = freqs[i]
                        if i_r < 480:
                            ymax_r = freqs3[i_r]
                        if i_l > 0:
                            ymax_l = freqs4[i_l]
                        xmax = i
                        ymax2 = freqs2[i]
                        ymax_label = ymax / 320.
                        xmax_label = xmax / 480.
                        # xmax_r = i+48
                        # xmax_l = i-48
                        if xmax_label < 0.5:
                            xmax_label = xmax_label + 0.1
                        else:
                            xmax_label = xmax_label - 0.1
                        global ymax2
                        global xmax_label
                        global ymax_label
                        global xmax
                        global ymax_r
                        global ymax_l
                        global i_r
                        global i_l
            pygame.draw.line(screen, freqshow.MARK_LINE,(xmax, 0), (xmax, 320))
            pygame.draw.line(screen, freqshow.MARK_LINE,((xmax - 5), ymax), ((xmax + 5), ymax))
            time.sleep(0.2)
            puase_str = self.model.get_puase_string()
            threshold = self.model.get_threshold()
            if (ymax2 > threshold)and(ymax_r > (threshold - 10))and(ymax_l > (threshold - 10)):
                freq = self.model.get_center_freq()
                bandwidth = self.model.get_sample_rate()
                xmax2 = freq - bandwidth * (0.5 - (xmax / 480))
                if xmax2 > 108:
                    self.controller.instant_change()
            else:
                self.model.set_center_freq(self.model.get_center_freq() + sw_step)
        else:
            sw_start = self.model.get_start_sweep()
            self.model.set_center_freq(sw_start)
            # Grab spectrogram data.
            freqs = self.model.get_data()
            # Scale frequency values to fit on the screen based on the min and max
            # intensity values.
            x, y, width, height = screen.get_rect()
            freqs = height - \
                np.floor(((freqs - self.model.min_intensity) /
                          self.model.range) * height)
            # Render frequency graph.
            screen.fill(freqshow.MAIN_BG)
            # Draw line segments to join each FFT result bin.
            ylast = freqs[0]
            ymax = 320
            # for i in range(1, width):
            # y = freqs[i]
            # pygame.draw.line(screen, freqshow.INSTANT_LINE, (i-1, ylast), (i, y))
            # ylast = y
            time.sleep(0.2)

class JustInstantSpectrogram(SpectrogramBase):
    """Instantaneous point in time line plot of the spectrogram."""

    def __init__(self, model, controller):
        self.count = 0
        super(JustInstantSpectrogram, self).__init__(model, controller)

    def render_spectrogram(self, screen):
        # print('just render')
		# Grab spectrogram data.
        freqs = self.model.get_data()
		# Scale frequency values to fit on the screen based on the min and max
		# intensity values.
        x, y, width, height = screen.get_rect()
        freqs2 = freqs
        freqs3 = freqs
        freqs4 = freqs
        freqs = height - np.floor(((freqs - self.model.min_intensity) / self.model.range) * height)
		# Render frequency graph.
        screen.fill(freqshow.MAIN_BG)
		# Draw line segments to join each FFT result bin.
        ylast = freqs[0]
        ymax = 320
        # print(len(freqs))
        for i in range(1, width):
            y = freqs[i]
            pygame.draw.line(screen, freqshow.INSTANT_LINE,(i - 1, ylast), (i, y))
            ylast = y
            if i > 0:
                if freqs[i] < ymax:
                    i_r = i + 24
                    i_l = i - 24
                    ymax = freqs[i]
                    if i_r < 480:
                        ymax_r = freqs3[i_r]
                    if i_l > 0:
                        ymax_l = freqs4[i_l]
                    xmax = i
                    ymax2 = freqs2[i]
                    ymax_label = ymax / 320.
                    xmax_label = xmax / 480.
                    # xmax_r = i+48
                    # xmax_l = i-48
                    if xmax_label < 0.5:
                        xmax_label = xmax_label + 0.1
                    else:
                        xmax_label = xmax_label - 0.1
                    global ymax2
                    global xmax_label
                    global ymax_label
                    global xmax
                    global ymax_r
                    global ymax_l
                    global i_r
                    global i_l
        pygame.draw.line(screen, freqshow.MARK_LINE,(xmax, 0), (xmax, 320))
        pygame.draw.line(screen, freqshow.MARK_LINE,((xmax - 5), ymax), ((xmax + 5), ymax))
        time.sleep(0.2)
        puase_str = self.model.get_puase_string()
        threshold = self.model.get_threshold()
        # print("ymax2: ")
        # print(ymax2)
        # print(" Threshold: ")
        # print(threshold)
        # print("ymax_r: ")
        # print(ymax_r)
        # print(" Threshold - 10: ")
        # print(threshold - 10)
        # print("ymax_l: ")
        # print(ymax_l)
        # print(" Threshold - 10: ")
        # print(threshold - 10)
        if (ymax2 > threshold)and(ymax_r > (threshold - 10))and(ymax_l > (threshold - 10)):
            freq = self.model.get_center_freq()
            bandwidth = self.model.get_sample_rate()
            xmax2 = freq - bandwidth * (0.5 - (xmax / 480))
            print(xmax2)
            if xmax2 > 108:
                if self.count == 10:
                    print(str(self.count) + " in if count")
                    self.model.set_puase_intensity('ENABLE')
                    #LINE_ACCESS_TOKEN = "bqcrEdUNzesoqYp5XI7huzhkxuFpKZhnLtc3I423BqE"
                    LINE_ACCESS_TOKEN = "LL3fyk42w0TwckIBQa1KhJSQWKR2Wu4NNQGxCbor301"
                    url = "https://notify-api.line.me/api/notify"

                    freq = self.model.get_center_freq()
                    bandwidth = self.model.get_sample_rate()
                    xmax2 = freq - bandwidth * (0.5 - (xmax / 480))

                    message = "Frequency " + \
                        str(xmax2) + "   Amplitude " + \
                        str(ymax2) + " For " +str(self.count) + \
                        " Sec\n" + "FM "+self.station_name+" MHz\n\nLATITUDE: \nLONGITUDE: \nรหัสสถานี: "
                    msg = urllib.urlencode(({"message": message}))
                    LINE_HEADERS = {'Content-Type': 'application/x-www-form-urlencoded',
                                    "Authorization": "Bearer " + LINE_ACCESS_TOKEN}
                    session = requests.Session()
                    a = session.post(url, headers=LINE_HEADERS, data=msg)
                    print(a.text)
                    #####
                    self.model.set_center_freq(self.model.get_center_freq() + (0.5 * bandwidth))
                    #####
                    self.count = 0
                else:
                    self.count += 1
                    print(str(self.count) + " else")
                    time.sleep(1)
        


class InstantSpectrogram(SpectrogramBase):
    """Instantaneous point in time line plot of the spectrogram."""

    def __init__(self, model, controller):
        self.count = 0
        super(InstantSpectrogram, self).__init__(model, controller)

    def render_spectrogram(self, screen):
        # Grab spectrogram data.
        print('instant')
        freqs = self.model.get_data()
        # Scale frequency values to fit on the screen based on the min and max
        # intensity values.
        x, y, width, height = screen.get_rect()
        freqs2 = freqs
        freqs = height - \
            np.floor(((freqs - self.model.min_intensity) /
                      self.model.range) * height)
        # Render frequency graph.
        screen.fill(freqshow.MAIN_BG)
        # Draw line segments to join each FFT result bin.
        ylast = freqs[0]
        ymax = 320
        for i in range(1, width):
            y = freqs[i]
            pygame.draw.line(screen, freqshow.INSTANT_LINE,
                             (i - 1, ylast), (i, y))
            ylast = y
            if i > 0:
                if freqs[i] < ymax:
                    ymax = freqs[i]
                    xmax = i
                    ymax2 = freqs2[i]
                    ymax_label = ymax / 320.
                    xmax_label = xmax / 480.
                    if xmax_label < 0.5:
                        xmax_label = xmax_label + 0.1
                    else:
                        xmax_label = xmax_label - 0.1
                    global ymax2
                    global xmax_label
                    global ymax_label
                    global xmax
                    global ymax_r
                    global ymax_l
                    global i_r
                    global i_l

        pygame.draw.line(screen, freqshow.MARK_LINE, (xmax, 0), (xmax, 320))
        pygame.draw.line(screen, freqshow.MARK_LINE, ((xmax - 5), ymax), ((xmax + 5), ymax))

        puase_str = self.model.get_puase_string()
        threshold = self.model.get_threshold()
        threshold = self.model.get_threshold()
        time.sleep(0.2)
        if (ymax2 > threshold)and(ymax_r > (threshold - 10))and(ymax_l > (threshold - 10)):
            freq = self.model.get_center_freq()
            bandwidth = self.model.get_sample_rate()
            xmax2 = freq - bandwidth * (0.5 - (xmax / 480))
            if xmax2 > 108:
                if self.count == 10:
                    print(str(self.count) + " in if count")
                    self.model.set_puase_intensity('ENABLE')
                    #LINE_ACCESS_TOKEN = "bqcrEdUNzesoqYp5XI7huzhkxuFpKZhnLtc3I423BqE"
                    LINE_ACCESS_TOKEN = "LL3fyk42w0TwckIBQa1KhJSQWKR2Wu4NNQGxCbor301"
                    url = "https://notify-api.line.me/api/notify"

                    freq = self.model.get_center_freq()
                    bandwidth = self.model.get_sample_rate()
                    xmax2 = freq - bandwidth * (0.5 - (xmax / 480))

                    message = "\nFrequency \n" + str(xmax2) + "\nAmplitude \n" + str(ymax2) + "\nFor " +str(self.count) + \
                        " Sec\n" + "FM "+self.model.station_frequency+" MHz\n"+self.model.station_name+"\nLATITUDE:\n"+ self.model.station_latitude+"\nLONGITUDE:\n"+self.model.station_longitude+"\nรหัสสถานี: "+self.model.station_code
                    msg = urllib.urlencode(({"message": message}))
                    LINE_HEADERS = {'Content-Type': 'application/x-www-form-urlencoded',
                                    "Authorization": "Bearer " + LINE_ACCESS_TOKEN}
                    session = requests.Session()
                    a = session.post(url, headers=LINE_HEADERS, data=msg)
                    print(a.text)
                    #####
                    self.model.set_center_freq(self.model.get_center_freq() + (0.5 * bandwidth))
                    #####
                    self.count = 0
                    self.controller.sweep_change()
                else:
                    self.count += 1
                    print(str(self.count) + " else")
                    time.sleep(1)
            else:
                self.controller.sweep_change()
