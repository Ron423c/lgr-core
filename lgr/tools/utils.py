# -*- coding: utf-8 -*-
"""
utils - List of utility functions for tools.
"""
from __future__ import unicode_literals

import logging

from lgr.parser.xml_parser import XMLParser

from lgr.exceptions import LGRInvalidLabelException, LGRLabelCollisionException
from lgr.tools.merge_set import merge_lgr_set
from lgr.tools.diff_collisions import is_collision

logger = logging.getLogger(__name__)


def read_labels(input, unidb, do_raise=False, keep_commented=False):
    """
    Read a label file and format lines to get a list of correct labels

    :param input: The name of the file containing the labels, as an iterator of Unicode strings.
    :param unidb: The UnicodeDatabase
    :param do_raise: Whether the label parsing exceptions are raised or not
    :param keep_commented: Whether commented labels are returned (still commented) or not
    :return: The list of labels as unicode strings
    """
    # Compute index label
    labels = map(lambda x: x.strip(), input)

    # remove comments
    for label in labels:
        if '#' in label:
            pos = label.find('#')
            if pos == 0:
                if keep_commented:
                    yield label
                continue
            label = label[:pos].strip()
        if len(label) == 0:
            continue

        # transform U-label and A-label in unicode strings
        try:
            label = parse_label_input(label, unidb.idna_decode_label, False)
        except BaseException as ex:
            if do_raise:
                raise
            label = "{}: {}".format(label, unicode(ex))
        yield label


def read_set_labels(merged_lgr, labels, validate_labels=True, do_raise=False):
    """
    Given a merged common LGR and a list of labels, read the labels and validate them against the common LGR.

    :param merged_lgr: Merged common LGR.
    :param labels: Iterator of labels.
    :param validate_labels: Whether the set labels should be validated in the merged LGR
    :param do_raise: Whether the label parsing exceptions are raised or not
    :return: The LGR set labels
    """
    set_labels = set()
    for label in read_labels(labels, merged_lgr.unicode_database, do_raise=do_raise):
        if validate_labels:
            label_cp = tuple([ord(c) for c in label])
            (eligible, __, __, __, __, logs) = merged_lgr.test_label_eligible(label_cp)
            if not eligible:
                logger.error('Label %s from LGR set labels is not valid: %s' % (label, logs.strip().split('\n')[-1]))
                if do_raise:
                    raise LGRInvalidLabelException(label, logs.strip().split('\n')[-1])
                else:
                    continue

        set_labels.add(label)

    if validate_labels:
        if is_collision(merged_lgr, set_labels):
            logger.error('Input label file contains collision(s)')
            if do_raise:
                raise LGRLabelCollisionException

    return set_labels


def parse_single_cp_input(s):
    """
    Parses a single code points from user input

    :param s: input
    :return: code point

    >>> parse_single_cp_input('z') == ord('z')  # treat single character as a character
    True
    >>> parse_single_cp_input('1') == ord('1')  # treat single character as a character, even if it is numeric
    True
    >>> parse_single_cp_input('a') == ord('a')  # treat single character as a character, even if it looks like hex
    True

    >>> parse_single_cp_input('U+1')  # U+ always treated as hex
    1
    >>> parse_single_cp_input('u+1')  # U+ can be lowercase
    1
    >>> parse_single_cp_input(' u+1')  # leading space ok
    1
    >>> parse_single_cp_input('u+1 ')  # trailing space ok
    1
    >>> parse_single_cp_input(' u+1 ')  # leading and trailing spaces ok
    1
    >>> parse_single_cp_input('U+10')
    16
    >>> parse_single_cp_input('U+10ffff') == 0x10FFFF
    True
    >>> parse_single_cp_input('U+10FFFF') == 0x10FFFF
    True
    >>> parse_single_cp_input('U+110000')  # overflow
    Traceback (most recent call last):
    ...
    ValueError: code point value must be in the range [0, U+10FFFF]
    >>> parse_single_cp_input('U+')  # short
    Traceback (most recent call last):
    ...
    ValueError: invalid literal for int() with base 16: ''
    >>> parse_single_cp_input('0061 0062')  # too many values
    Traceback (most recent call last):
    ...
    ValueError: invalid literal for int() with base 16: '0061 0062'
    """
    s = s.strip()
    if len(s) == 1:
        # unicode char
        return ord(s)
    else:
        if s[:2].upper() == 'U+':
            # U+XXXX
            v = int(s[2:], 16)
        else:
            v = int(s, 16)

        # check bounds
        if v < 0 or v > 0x10FFFF:
            raise ValueError("code point value must be in the range [0, U+10FFFF]")

        return v


def parse_codepoint_input(s):
    """
    Parses a code point or sequence of code points from user input

    :param s: input
    :return: list of code points

    >>> parse_codepoint_input('0061')
    [97]
    >>> parse_codepoint_input('0061 0062')
    [97, 98]
    >>> parse_codepoint_input('0061    0062')
    [97, 98]

    >>> parse_codepoint_input('a')
    [97]
    >>> parse_codepoint_input('a b')
    [97, 98]

    >>> parse_codepoint_input('U+0061 U+0062')
    [97, 98]
    >>> parse_codepoint_input('U+0061 0062')
    [97, 98]
    """
    return [parse_single_cp_input(x) for x in s.split()]


def parse_label_input(s, idna_decoder=lambda x: x.decode('idna'), as_cp=True):
    """
    Parses a label from user input, applying a bit of auto-detection smarts

    :param s: input string in A-label, U-label or space-separated hex sequences.
    :param idna_decoder: IDNA decode function.
    :param as_cp: If True, returns a list of code points. Otherwise, unicode string.
    :return: list of code points

    >>> parse_label_input('0061')  # treated as U-label - probably the only confusing result
    [48, 48, 54, 49]
    >>> parse_label_input('U+0061')  # this is how to signal that you want hex
    [97]
    >>> parse_label_input('abc')
    [97, 98, 99]
    >>> parse_label_input('a b c')
    [97, 98, 99]
    >>> parse_label_input('xn--m-0ga')  # "öm"
    [246, 109]
    """
    if s.lower().startswith('xn--'):
        if as_cp:
            return [ord(c) for c in idna_decoder(s.lower())]
        else:
            return idna_decoder(s.lower())
    elif ' ' in s or 'U+' in s.upper():
        try:
            label_cp = parse_codepoint_input(s)
        except:
            if ' ' in s:
                raise ValueError("Label '{}' contains spaces "
                                 "that are not PVALID for IDNA2008".format(s))
            raise
        if as_cp:
            return label_cp
        else:
            return ''.join([unichr(c) for c in label_cp])
    else:
        # treat as unicode
        if as_cp:
            return [ord(c) for c in s]
        else:
            return s


def write_output(s, test=True):
    if test:
        print(s.encode('utf-8'))


def merge_lgrs(input_lgrs, name=None, rng=None, unidb=None):
    """
    Merge LGRs to create a LGR set

    :param input_lgrs: The LGRs belonging to the set
    :param name: The merged LGR name
    :param rng: The RNG file to validate input LGRs
    :param unidb: The unicode database
    :return: The merged LGR and the LGRs in the set.
    """
    lgr_set = []
    for lgr_file in input_lgrs:
        lgr_parser = XMLParser(lgr_file)
        if unidb:
            lgr_parser.unicode_database = unidb

        if rng:
            validation_result = lgr_parser.validate_document(rng)
            if validation_result is not None:
                logger.error('Errors for RNG validation of LGR %s: %s',
                             lgr_file, validation_result)

        lgr = lgr_parser.parse_document()
        if lgr is None:
            logger.error("Error while parsing LGR file %s." % lgr_file)
            logger.error("Please check compliance with RNG.")
            return

        lgr_set.append(lgr)

    if not name:
        name = 'merged-lgr-set'

    merged_lgr = merge_lgr_set(lgr_set, name)
    if unidb:
        merged_lgr.unicode_database = unidb

    return merged_lgr, lgr_set
