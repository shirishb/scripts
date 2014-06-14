#! /usr/bin/env python3.4

import sys
import argparse
import logging as log
import os
import hashlib
import pprint

LIST=True
DELETE=False
IGNORE_HIDDEN=True
IGNORE_SYMLINKS=True

class File():
	def __init__(self, filename, root):
		self.__filename = filename
		self.__root = root
		self.__size = 0
		self.__hash = 0

	def __str__(self):
		return "{}, {} ({} bytes)".format(self.__root, self.__filename, self.__size)

	def calculate(self):
		filepath = os.path.join(self.__root, self.__filename)
		self.__size = os.path.getsize(filepath)

		# Thanks: http://stackoverflow.com/questions/1131220/get-md5-hash-of-big-files-in-python
		md5 = hashlib.md5()
		with open(filepath,'rb') as f: 
			for chunk in iter(lambda: f.read(md5.block_size), b''): 
				 md5.update(chunk)
		self.__hash = md5.hexdigest()

	def getHash(self):
		return self.__hash

def generateFileList(directories):
	filelist = []
	for directory in directories:
		for root, dirs, files in os.walk(directory):
			# Prune directory list as required
			for d in dirs:
				dirpath = os.path.join(root, d)
				if not os.path.exists(dirpath):
					log.warn("directory {} does not exist".format(d))
					dirs.remove(d)
				if IGNORE_HIDDEN and d.startswith('.'):
					log.warn("removing hidden directory {}".format(d))
					dirs.remove(d)
				if IGNORE_SYMLINKS and os.path.islink(dirpath):
					log.warn("removing symlinked directory {}".format(d))
					dirs.remove(d)

			for f in files:
				if IGNORE_HIDDEN and f.startswith('.'):
					continue
				filepath = os.path.join(root, f)
				if not os.path.exists(filepath):
					continue
				if IGNORE_SYMLINKS and os.path.islink(filepath):
					continue
				filelist.append( File(f, root))
	return filelist

def generateFileDictionary(fileList):
	fileDictionary = {}
	for f in fileList:
		f.calculate()
		if f.getHash() in fileDictionary.keys():
			fileDictionary[f.getHash()].append(f)
		else:
			fileDictionary[f.getHash()] = [ f ]
	return fileDictionary


def main():
	log.basicConfig(level=log.DEBUG, format='%(levelname)s: %(message)s')
	parser = argparse.ArgumentParser()
	parser.add_argument('--directory', '-d', nargs='*', required=True)
	parser.add_argument('--verbose', '-v', action='count', default=0)
	args = parser.parse_args()
	print(args)

	fileList = generateFileList(args.directory)

	print("{} files read".format(len(fileList)))

	fileDictionary = generateFileDictionary(fileList)

	for hash, files in fileDictionary.items():
		if len(files) > 1:
			print(hash + ":")
			for f in files:
				print("\t{}".format(f))


if __name__ == '__main__':
	main()