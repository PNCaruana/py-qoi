import io


class qoi_header:

    def __init__(self, width=0, height=0, channels=3, colorspace=0):
        self.magic = intToBinary(ord("q"), 8) + intToBinary(ord("0"), 8) + intToBinary(ord("i"), 8) + intToBinary(ord("f"), 8)  # qoif in binary ASCII
        self.width = intToBinary(width, 32)  # 32 bit uint
        self.height = intToBinary(height, 32)  # 32 bit uint
        self.channels = intToBinary(channels, 8)  # uint8
        self.colorspace = intToBinary(colorspace, 8)  # uint8


    def toString(self):
        return self.magic + self.width + self.height + self.channels + self.colorspace

# Chunk type specifications
class QOI_OP_RGB:
    def __init__(self, pixel):
        self.Byte0 = "11111110"  # Tag
        self.Byte1 = intToBinary(pixel[0],8)  # Red Channel
        self.Byte2 = intToBinary(pixel[1],8)  # Green Channel
        self.Byte3 = intToBinary(pixel[2],8)  # Blue Channel



    def toString(self):
        return self.Byte0 + self.Byte1 + self.Byte2 + self.Byte3

class QOI_OP_INDEX:
    def __init__(self, index):
        self.tag = "00"
        self.index = intToBinary(index, 6)

    def toString(self):
        return self.tag + self.index

class QOI_OP_DIFF:
    def __init__(self, diff):
        self.tag = "01"

        dr = diff[0]
        dg = diff[1]
        db = diff[2]

        self.dr = intToBinary(dr, 2, signed=True, bias=2)
        self.dg = intToBinary(dg, 2, signed=True, bias=2)
        self.db = intToBinary(db, 2, signed=True, bias=2)


    def toString(self):
        return self.tag + self.dr + self.dg + self.db

class QOI_OP_LUMA:
    def __init__(self, diff):
        self.tag = "10"

        dg = diff[1]
        drdg = diff[0] - diff[1]
        dbdg = diff[2] - diff[1]

        self.dg = intToBinary(dg, 6, signed=True, bias=32)        #  6 bit green channel difference from the previous pixel -32 to 31
        self.drdg = intToBinary(drdg, 4, signed=True, bias=8)     #  4 bit red channel difference minus green channel difference -8 to 7
        self.dbdg = intToBinary(dbdg, 4, signed=True, bias=8)     #  4 bit blue channel difference minus green channel difference -8 to 7


    def toString(self):
        return self.tag + self.dg + self.drdg + self.dbdg

class QOI_OP_RUN:
    def __init__(self, runlength):
        self.tag = "11"
        self.run = intToBinary(runlength,6)

    def toString(self):
        return self.tag + self.run

class qoi_hash_table:

    def __init__(self):
        self.arr = [None] * 64

    def add(self, pixel):
        r = pixel[0]
        g = pixel[1]
        b = pixel[2]

        # Position is given as a function of hash
        index_position = (r*3 + g*5 + b*7) % 64
        self.arr[index_position] = pixel

        return index_position

    def get(self, pixel):
        r = pixel[0]
        g = pixel[1]
        b = pixel[2]

        # Position is given as a function of hash
        index_position = (r * 3 + g * 5 + b * 7) % 64
        return self.arr[index_position], index_position

def intToBinary(val, size=8, signed=False, bias=0):
    if not signed:
        binVal = "{0:b}".format(val)
        return binVal.rjust(size, '0')

    if signed:
        val += bias
        binVal = "{0:b}".format(val)
        return binVal.rjust(size, '0')

def flattenImage(img):
    X = len(img)
    Y = len(img[0])
    flat = []
    for x in range(0,X):
        for y in range(0,Y):
            flat.append(img[x,y])

    return flat

def write(filename, img, debug=False):
    if debug: print("Attempting to write" + filename + " ...")


    # Ensure colour channels are either 3 or 4 channels
    imgC = img.copy()
    if len(imgC.shape) == 2:
        if debug: print("Image is grayscale, converting to 3 channel RGB")
        imgC = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)

    shape = imgC.shape
    header = qoi_header(width=shape[0], height=shape[1], channels=3)

    # Begin encoding
    chunks = []  # List of all chunks in order
    chunks.append(header)
    pTable = qoi_hash_table()  # Length 64 hash table storing pixel values that we've seen before
    prev = [0, 0, 0]
    PX = flattenImage(imgC)  # Flatten image into a stream of pixels
    i = 0
    N = len(PX)
    while i < N:
        if debug: print("<<<<<< encoding... " + "{0:d}/{1:d}".format(i+1, N) + " >>>>>>")
        # First try to encode via runlength QOI_OP_RUN (Max runlength is 62)
        # If current != prevPixel, then try to store QOI_OP_DIFF if its small enough diff, or QOI_OP_LUMA for large
        # If that doesnt work, lets try the hash list QOI_OP_INDEX
        # And finally, if theres an issue then we just store the rgb info QOI_OP_RGB

        curr = PX[i]
        if debug: print(" > previous pixel: " + str(prev))
        if debug: print(" > current pixel: " + str(curr))
        # QOI_OP_RUN
        if (prev==curr).all():
            if debug: print(" >> prev is same as current pixel, computing run")
            runLength = 1
            while runLength <= 62 and (i + runLength < N):
                curr = PX[i + runLength]
                if debug: print("  >> curr @ " + str(i + runLength) + " is " + str(curr))
                if (prev==curr).all():
                    runLength += 1 #increment length
                else:
                    if debug: print("  >> curr @ " + str(i + runLength) + " does not match. Ending run")
                    break
            chunk = QOI_OP_RUN(runLength)
            chunks.append(chunk)
            if debug: print("  >> final run length is " + str(runLength))
            i += runLength + 1 # Skip ahead the length of the run
            continue # move to next iteration in the loop, only one chunk can be added per turn

        # QOI_OP_DIFF
        diff = curr - prev
        is_diff = all(-2 <= x <= 1 for x in diff)
        if is_diff:
            if debug: print(" > Small Difference detected : " + str(diff))
            # Difference is small enough
            chunk = QOI_OP_DIFF(diff)
            chunks.append(chunk)
            # Now set up for the next loop
            i += 1
            prev = curr
            continue  # move to next loop iteration
        elif (-32 <= diff[1] <= 31) and (-8 <= diff[0] <= 7) and (-8 <= diff[2] <= 7):
            if debug: print(" > Large Difference detected : " + str(diff))
            # Larger difference, but within params so we can do QOI_OP_LUMA
            chunk = QOI_OP_LUMA(diff)
            chunks.append(chunk)
            # Now set up for the next loop
            i += 1
            prev = curr
            continue  # move to next loop iteration

        # QOI_OP_INDEX
        # First, check hash has a value at it. If it doesnt, then set previous[index] = curr
        # If it does have a value, is it the same as curr? if so then QOI_OP_INDEX.
        # If not, then we'll have to resort to QOI_OP_RGB
        tableVal, index = pTable.get(curr)
        if tableVal is None:
            if debug: print(" > current pixel hashes to empty space. Adding to table")

            index = pTable.add(curr)  # qoi_hash_table returns the index of the pixel supplied to it
            chunk = QOI_OP_RGB(curr)  # we need to save the value of this initial one, everything else in the table is based on it
            print(chunk.toString())
            chunks.append(chunk)
            # Now set up for the next loop
            i += 1
            prev = curr
            continue
        else:
            # Is that value at curr's hash the same as curr? Then we have a hit and can just reference that index
            tableVal, index = pTable.get(curr)
            if (tableVal==curr).all():
                if debug: print(" > current pixel hashes to spot which contains same value : table[i] = " + str(tableVal))

                chunk = QOI_OP_INDEX(index)
                chunks.append(chunk)
                # Now set up for the next loop
                i += 1
                prev = curr
                continue

        if debug: print(" > Saving as RGB chunk")

        # QOI_OP_RGB
        chunk = QOI_OP_RGB(curr)
        chunks.append(chunk)
        prev = curr
        i += 1
        # Will automatically loop since its a while loop


    # Write to file
    Bstring = ""
    for C in chunks:
        Bstring += C.toString()
    Bstring += intToBinary(1, 8*8)  # End of file indicator 7 byes of 0x00 and one byte of 0x01 i.e. 8 bytes = 8x8 bits
    B = int(Bstring, 2).to_bytes((len(Bstring) + 7) // 8, byteorder='big')  # Bytes from string of "01011101..." etc
    with open(filename, "wb") as file:
        file.write(B)

    if debug: print("Saved " + filename)

    return chunks

def read_chunk(file_obj, chunkSize=8):
    while True:
        file = file_obj.read(chunkSize)
        if not file:
            break
        yield file

def read(filename, flag=1):
    RGB_HEADER = b'\xFE'
    print(RGB)

    file = open(filename, "rb")
    buffer = io.BytesIO()
    for chunk in read_chunk(file, chunkSize=1):
        print(chunk)
        buffer.write(chunk)
    buffer.seek(0)
    for B in buffer:



if __name__ == "__main__":
    print("Quite Ok Image Format...Testing")

    read("A.qoi")

