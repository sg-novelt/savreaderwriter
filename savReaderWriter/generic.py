#!/usr/bin/env python
# -*- coding: utf-8 -*-

from savReaderWriter import *

class Generic(object):
    """
    Class for methods and data used in reading as well as writing
    IBM SPSS Statistics data files
    """

    def __init__(self, savFileName, ioUtf8=False, ioLocale=None):
        """Constructor. Note that interface locale and encoding can only
        be set once"""
        locale.setlocale(locale.LC_ALL, "")
        self.savFileName = savFileName
        self.libc = cdll.LoadLibrary(ctypes.util.find_library("c"))
        self.spssio = self.loadLibrary()

        self.wholeCaseIn = self.spssio.spssWholeCaseIn
        self.wholeCaseOut = self.spssio.spssWholeCaseOut

        self.encoding_and_locale_set = False
        if not self.encoding_and_locale_set:
            self.encoding_and_locale_set = True
            self.ioLocale = ioLocale
            self.ioUtf8 = ioUtf8

    def _encodeFileName(self, fn):
        """Helper function to encode unicode file names into bytestring file
        names encoded in the file system's encoding. Needed for C functions
        that have a c_char_p filename argument.
        http://effbot.org/pyref/sys.getfilesystemencoding.htm
        http://docs.python.org/2/howto/unicode.html under 'unicode filenames'"""
        if not isinstance(fn, unicode):
            return fn
        elif sys.platform.startswith("win"):
            return self.wide2utf8(fn)
        else:
            encoding = sys.getfilesystemencoding()
            encoding = "utf-8" if not encoding else encoding  # actually, ascii
        try:
            return fn.encode(encoding)
        except UnicodeEncodeError, e:
            msg = ("File system encoding %r can not be used to " +
                   "encode file name %r [%s]")
            raise ValueError(msg % (encoding, fn, e))

    def loadLibrary(self):
        """This function loads and returns the SPSSIO libraries,
        depending on the platform."""
        is_32bit = platform.architecture()[0] == "32bit"
        pf = sys.platform.lower()
        load = WinDLL if pf.startswith("win") else CDLL
        oldpath = os.getcwd()
        path = os.path.dirname( __file__ )
        chdir = lambda loc: os.chdir(os.path.join(path, "spssio", loc))
        try:
            if pf.startswith("win") and is_32bit:
                chdir("win32")
                spssio = load("spssio32.dll") 
            elif pf.startswith("win"):
                chdir("win64")
                spssio = load("spssio64.dll")
            elif pf.startswith("lin"):  # most linux flavours, incl zLinux
                if is_32bit:
                    chdir("lin32")
                else:
                    chdir("lin64")
                # how to recognize zLinux?
                spssio = load("libspssdio.so.1")
            elif pf.startswith("darwin") or pf.startswith("mac"):
                chdir("macos")
                spssio = load("libspssdio.dylib")
            elif pf.startswith("aix") and not is_32bit:
                chdir("aix64")
                spssio = load("libspssdio.so.1")
            elif pf.startswith("hp-ux"):
                chdir("hpux_it")
                spssio = load("libspssdio.sl.1")
            elif pf.startswith("sunos") and not is_32bit:
                chdir("sol64")
                spssio = load("libspssdio.so.1")
            else:
                msg = "Your platform (%r) is not supported" % pf
                raise NotImplementedError(msg)
        finally:
            os.chdir(oldpath)
        return spssio

    def errcheck(self, res, func, args):
        """This function checks for errors during the execution of
        function <func>"""
        if not res:
            msg = "Error performing %r operation on file %r."
            raise IOError(msg % (func.__name__, self.savFileName))
        return res

    def wide2utf8(self, fn):
        """Take a unicode file name string and encode it to a multibyte string
        that Windows can use to represent file names (CP65001, UTF-8)
        http://msdn.microsoft.com/en-us/library/windows/desktop/dd374130"""

        from ctypes import wintypes

        _CP_UTF8 = 65001
        _CP_ACP = 0  # ANSI
        _LPBOOL = POINTER(c_long)

        _wideCharToMultiByte = windll.kernel32.WideCharToMultiByte
        _wideCharToMultiByte.restype = c_int
        _wideCharToMultiByte.argtypes = [wintypes.UINT, wintypes.DWORD,
            wintypes.LPCWSTR, c_int, wintypes.LPSTR, c_int, wintypes.LPCSTR, _LPBOOL]

        codePage = _CP_UTF8
        dwFlags = 0
        lpWideCharStr = fn
        cchWideChar = len(fn)
        lpMultiByteStr = None
        cbMultiByte = 0  # zero requests size
        lpDefaultChar = None
        lpUsedDefaultChar = None

        # get size
        mbcssize = _wideCharToMultiByte(
        codePage, dwFlags, lpWideCharStr, cchWideChar, lpMultiByteStr,
        cbMultiByte, lpDefaultChar, lpUsedDefaultChar)
        if mbcssize <= 0:
            raise WinError(mbcssize)
        lpMultiByteStr = create_string_buffer(mbcssize)

        # convert
        retcode = _wideCharToMultiByte(
        codePage, dwFlags, lpWideCharStr, cchWideChar, lpMultiByteStr,
        mbcssize, lpDefaultChar, lpUsedDefaultChar)
        if retcode <= 0:
            raise WinError(retcode)
        return lpMultiByteStr.value

    def openSavFile(self, savFileName, mode="rb", refSavFileName=None):
        """This function opens IBM SPSS Statistics data files in mode <mode>
        and returns a handle that  should be used for subsequent operations on
        the file. If <savFileName> is opened in mode "cp", meta data
        information aka the spss dictionary is copied from <refSavFileName>"""
        savFileName = os.path.abspath(savFileName)  # fdopen wants full name
        try:
            fdopen = self.libc._fdopen  # Windows
        except AttributeError:
            fdopen = self.libc.fdopen   # Linux and others
        fdopen.argtypes = [c_int, c_char_p]
        fdopen.restype = c_void_p
        fdopen.errcheck = self.errcheck
        mode_ = "wb" if mode == "cp" else mode
        with open(savFileName, mode_) as f:
            self.fd = fdopen(f.fileno(), mode_)
        if mode == "rb":
            spssOpen = self.spssio.spssOpenRead
        elif mode == "wb":
            spssOpen = self.spssio.spssOpenWrite
        elif mode == "cp":
            spssOpen = self.spssio.spssOpenWriteCopy
        elif mode == "ab":
            spssOpen = self.spssio.spssOpenAppend

        savFileName = self._encodeFileName(savFileName)
        refSavFileName = self._encodeFileName(refSavFileName)
        sav = c_char_p(savFileName)
        fh = c_int(self.fd)
        if mode == "cp":
            retcode = spssOpen(sav, c_char_p(refSavFileName), pointer(fh))
        else:
            retcode = spssOpen(sav, pointer(fh))

        if retcode > 0:
            msg = "Error opening file %r in mode %r"
            raise SPSSIOError(msg % (savFileName, mode), retcode)
        return fh.value

    def closeSavFile(self, fh, mode="rb"):
        """This function closes the sav file associated with <fh> that was open
        in mode <mode>."""
        if mode == "rb":
            spssClose = self.spssio.spssCloseRead
        elif mode == "wb":
            spssClose = self.spssio.spssCloseWrite
        elif mode == "ab":
            spssClose = self.spssio.spssCloseAppend
        retcode = spssClose(c_int(fh))
        if retcode > 0:
            raise SPSSIOError("Error closing file in mode %r" % mode, retcode)

##    def closeFile(self):
##        """Close file"""
##        try:
##            try:
##                # Windows
##                self.libc._close.errcheck = self.errcheck
##                self.libc._close(c_void_p(self.fd))
##            except AttributeError:
##                # Linux
##                self.libc.close.errcheck = self.errcheck
##                self.libc.close(c_void_p(self.fd))
##        except EnvironmentError, e:
##            print e

    @property
    def releaseInfo(self):
        """This function reports release- and machine-specific information
        about the open file."""
        relInfo = ["release number", "release subnumber", "fixpack number",
                   "machine code", "floating-point representation code",
                   "compression scheme code", "big/little-endian code",
                   "character representation code"]
        relInfoArr = (c_int * len(relInfo))()
        retcode = self.spssio.spssGetReleaseInfo(c_int(self.fh), relInfoArr)
        if retcode > 0:
            raise SPSSIOError("Error getting ReleaseInfo", retcode)
        info = dict([(item, relInfoArr[i]) for i, item in enumerate(relInfo)])
        return info

    @property
    def spssVersion(self):
        """Return the SPSS version that was used to create the opened file
        as a three-tuple indicating major, minor, and fixpack version as
        ints. NB: in the transition from SPSS to IBM, a new four-digit
        versioning nomenclature is used. This function returns the old
        three-digit nomenclature. Therefore, no patch version information
        is available."""
        info = self.releaseInfo
        major = info["release number"]
        minor = info["release subnumber"]
        fixpack = info["fixpack number"]
        return major, minor, fixpack

    @property
    def fileCompression(self):
        """Get/Set the file compression.
        Returns/Takes a compression switch which may be any of the following:
        'uncompressed', 'standard', or 'zlib'. Zlib comression requires SPSS
        v21 I/O files."""
        compression = {0: "uncompressed", 1: "standard", 2: "zlib"}
        compSwitch = c_int()
        func = self.spssio.spssGetCompression
        retcode = func(c_int(self.fh), byref(compSwitch))
        if retcode > 0:
            raise SPSSIOError("Error getting file compression", retcode)
        return compression.get(compSwitch.value)

    @fileCompression.setter
    def fileCompression(self, compSwitch):
        compression = {"uncompressed": 0, "standard": 1, "zlib": 2}
        compSwitch = compression.get(compSwitch)
        func = self.spssio.spssSetCompression
        retcode = func(c_int(self.fh), c_int(compSwitch))
        invalidSwitch = retcodes.get(retcode) == 'SPSS_INVALID_COMPSW'
        if invalidSwitch and self.spssVersion[0] < 21:
            msg = "Writing zcompressed files requires >=v21 SPSS I/O libraries"
            raise ValueError(msg)
        elif retcode > 0:
            raise SPSSIOError("Error setting file compression", retcode)

    @property
    def systemString(self):
        """This function returns the name of the system under which the file
        was created aa a string."""
        sysName = create_string_buffer(42)
        func = self.spssio.spssGetSystemString
        retcode = func(c_int(self.fh), byref(sysName))
        if retcode > 0:
            raise SPSSIOError("Error getting SystemString", retcode)
        return sysName.value

    def getStruct(self, varTypes, varNames, mode="rb"):
        """This function returns a compiled struct object. The required
        struct format string for the conversion between C and Python
        is created on the basis of varType and byte order.
        --varTypes: SPSS data files have either 8-byte doubles/floats or n-byte
          chars[]/ strings, where n is always 8 bytes or a multiple thereof.
        --byte order: files are written in the byte order of the host system
          (mode="wb") and read/appended using the byte order information
          contained in the SPSS data file (mode is "ab" or "rb" or "cp")"""
        if mode in ("ab", "rb", "cp"):     # derive endianness from file
            endianness = self.releaseInfo["big/little-endian code"]
            endianness = ">" if endianness > 0 else "<"
        elif mode == "wb":                 # derive endianness from host
            if sys.byteorder == "little":
                endianness = "<"
            elif sys.byteorder == "big":
                endianness = ">"
            else:
                endianness = "@"
        structFmt = [endianness]
        ceil = math.ceil
        for varName in varNames:
            varType = varTypes[varName]
            if varType == 0:
                structFmt.append("d")
            else:
                fmt = str(int(ceil(int(varType) / 8.0) * 8))
                structFmt.append(fmt + "s")
        return struct.Struct("".join(structFmt))

    def getCaseBuffer(self):
        """This function returns a buffer and a pointer to that buffer. A whole
        case will be read into this buffer."""
        caseSize = c_long()
        retcode = self.spssio.spssGetCaseSize(c_int(self.fh), byref(caseSize))
        caseBuffer = create_string_buffer(caseSize.value)
        if retcode > 0:
            raise SPSSIOError("Problem getting case buffer", retcode)
        return caseBuffer

    @property
    def sysmis(self):
        """This function returns the IBM SPSS Statistics system-missing
        value ($SYSMIS) for the host system (also called 'NA' in other
        systems)."""
        try:
            sysmis = -1 * sys.float_info[0]  # Python 2.6 and higher.
        except AttributeError:
            self.spssio.spssSysmisVal.restype = c_float
            sysmis = self.spssio.spssSysmisVal()
        return sysmis

    @property
    def missingValuesLowHigh(self):
        """This function returns the 'lowest' and 'highest' values used for
        numeric missing value ranges on the host system. This can be used in
        a similar way as the LO and HI keywords in missing values
        specifications (cf. MISSING VALUES foo (LO THRU 0). It may be called
        at any time."""
        lowest, highest = c_double(), c_double()
        func = self.spssio.spssLowHighVal
        retcode = func(byref(lowest), byref(highest))
        return lowest.value, highest.value

    @property
    def ioLocale(self):
        """This function gets/sets the I/O Module's locale.
        This corresponds with the SPSS command SET LOCALE. The I/O Module's
        locale is separate from that of the client application. The
        <localeName> parameter and the return value are identical to those
        for the C run-time function setlocale. The exact locale name
        specification depends on the OS of the host sytem, but has the
        following form:
                   <lang>_<territory>.<codeset>[@<modifiers>]
        The 'codeset' and 'modifier' components are optional and in Windows,
        aliases (e.g. 'english') may be used. When the I/O Module is first
        loaded, its locale is set to the system default. See also:
        --https://wiki.archlinux.org/index.php/Locale
        --http://msdn.microsoft.com/en-us/library/39cwe7zf(v=vs.80).aspx"""
        if hasattr(self, "setLocale"):
            return self.setLocale
        else:
            currLocale = ".".join(locale.getlocale())
            print "NOTE. Locale not set; getting current locale: ", currLocale
            return currLocale

    @ioLocale.setter
    def ioLocale(self, localeName=""):
        if not localeName:
            localeName = ".".join(locale.getlocale())
        func = self.spssio.spssSetLocale
        func.restype = c_char_p
        self.setLocale = func(c_int(locale.LC_ALL), c_char_p(localeName))
        if self.setLocale is None:
            raise ValueError("Invalid ioLocale: %r" % localeName)
        return self.setLocale

    @property
    def fileCodePage(self):
        """This function provides the Windows code page number of the encoding
        applicable to a file."""
        nCodePage = c_int()
        func = self.spssio.spssGetFileCodePage
        retcode = func(c_int(self.fh), byref(nCodePage))
        return nCodePage.value

    def isCompatibleEncoding(self):
        """This function determines whether the file and interface encoding
        are compatible."""
        try:
            # Windows, note typo 'Endoding'!
            func = self.spssio.spssIsCompatibleEndoding
        except AttributeError:
            func = self.spssio.spssIsCompatibleEncoding
        func.restype = c_bool
        isCompatible = c_int()
        retcode = func(c_int(self.fh), byref(isCompatible))
        if retcode > 0:
            msg = "Error testing encoding compatibility: %r"
            raise SPSSIOError(msg % isCompatible.value, retcode)
        if not isCompatible.value and not self.ioUtf8:
            msg = ("NOTE. SPSS Statistics data file %r is written in a " +
                   "character encoding (%s) incompatible with the current " +
                   "ioLocale setting. It may not be readable. Consider " +
                   "changing ioLocale or setting ioUtf8=True.")
            print msg % (self.savFileName, self.fileEncoding)
        return bool(isCompatible.value)

    @property
    def ioUtf8(self):
        """This function returns/sets the current interface encoding.
        ioUtf8 = False --> CODEPAGE mode,
        ioUtf8 = True --> UTF-8 mode, aka. Unicode mode
        This corresponds with the SPSS command SHOW UNICODE (getter)
        and SET UNICODE=ON/OFF (setter)."""
        if hasattr(self, "ioUtf8_"):
            return self.ioUtf8_
        self.ioUtf8_ = self.spssio.spssGetInterfaceEncoding()
        return bool(self.ioUtf8_)

    @ioUtf8.setter
    def ioUtf8(self, ioUtf8):
        try:
            retcode = self.spssio.spssSetInterfaceEncoding(c_int(int(ioUtf8)))
            if retcode > 0 and not self.encoding_and_locale_set:
                # not self.encoding_and_locale_set --> nested context managers
                raise SPSSIOError("Error setting IO interface", retcode)
        except TypeError:
            msg = "Invalid interface encoding: %r (must be bool)"
            raise SPSSIOError(msg % ioUtf8)

    @property
    def fileEncoding(self):
        """This function obtains the encoding applicable to a file.
        The encoding is returned as an IANA encoding name, such as
        ISO-8859-1, which is then converted to the corresponding Python
        codec name. If the file contains no file encoding, the locale's
        preferred encoding is returned"""
        preferredEncoding = locale.getpreferredencoding()
        try:
            pszEncoding = create_string_buffer(20)  # is 20 enough??
            func = self.spssio.spssGetFileEncoding
            retcode = func(c_int(self.fh), byref(pszEncoding))
            if retcode > 0:
                raise SPSSIOError("Error getting file encoding", retcode)
            iana_codes = encodings.aliases.aliases
            rawEncoding = pszEncoding.value.lower()
            if rawEncoding.replace("-", "") in iana_codes:
                iana_code = rawEncoding.replace("-", "")
            else:
                iana_code = rawEncoding.replace("-", "_")
            fileEncoding = iana_codes[iana_code]
            return fileEncoding
        except AttributeError:
            print ("NOTE. Function 'getFileEncoding' not found. You are " +
                   "using a .dll from SPSS < v16.")
            return preferredEncoding
        except KeyError:
            print ("NOTE. IANA coding lookup error. Code %r " % iana_code +
                   "does not map to any Python codec.")
            return preferredEncoding

    @property
    def record(self):
        """Get/Set a whole record from/to a pre-allocated buffer"""
        retcode = self.wholeCaseIn(c_int(self.fh),
                                   byref(self.caseBuffer))
        if retcode > 0:
            raise SPSSIOError("Problem reading row", retcode)
        record = list(self.unpack_from(self.caseBuffer))
        return record

    @record.setter
    def record(self, record):
        try:
            self.pack_into(self.caseBuffer, 0, *record)
        except struct.error, e:
            msg = "Use ioUtf8=True to write unicode strings [%s]" % e
            raise TypeError(msg)
        retcode = self.wholeCaseOut(c_int(self.fh),
                                    c_char_p(self.caseBuffer.raw))
        if retcode > 0:
            raise SPSSIOError("Problem writing row:\n" + \
                              unicode(record, "utf-8"), retcode)

    def printPctProgress(self, nominator, denominator):
        """This function prints the % progress when reading and writing
        files"""
        if nominator and nominator % 10**4 == 0:
            pctProgress = (float(nominator) / denominator) * 100
            print "%2.1f%%... " % pctProgress,