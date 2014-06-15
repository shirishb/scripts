#! /usr/bin/env python3.4

import sys
import argparse
import logging as log
import os
import hashlib
import fnmatch
import pickle

LIST=True
DELETE=False
IGNORE_HIDDEN=True
IGNORE_SYMLINKS=True
PERSIST_FILELIST=True
PERSIST_FILENAME='dedup.filelist'

class File():
	def __init__(self, filename, root):
		self.__filename = filename
		self.__root = root
		self.__hash = None
		self.__size = None
		self.__modified_timestamp = None

	def __str__(self):
		return "{}, {} ({} bytes)".format(self.__root, self.__filename, self.__size)

	def update(self, file):
		if self.__filename == file.__filename:
			if self.__root == file.__root:
				self.__hash = file.__hash
				self.__size = file.__size
				self.__modified_timestamp = file.__modified_timestamp

	# note: method assumes that file exists
	def calculate(self):
		filepath = os.path.join(self.__root, self.__filename)

		if self.__hash is not None:
			if self.__modified_timestamp == os.path.getmtime(filepath):
				return # nothing to do as file has not changed


		self.__size = os.path.getsize(filepath)
		self.__modified_timestamp = os.path.getmtime(filepath)

		# Thanks: http://stackoverflow.com/questions/1131220/get-md5-hash-of-big-files-in-python
		md5 = hashlib.md5()
		with open(filepath,'rb') as f: 
			for chunk in iter(lambda: f.read(md5.block_size * 4), b''): 
				 md5.update(chunk)
		self.__hash = md5.hexdigest()

	def getHash(self):
		return self.__hash

	def getFilePath(self):
		return os.path.join(self.__root, self.__filename)

def generateFileList(directoryList, ignoreList, filterList):
	fileList = []
	for directory in directoryList:
		for root, dirs, files in os.walk(directory, topdown=True):
			# Prune directory list as per script configuration
            # Removes invalid, hidden or symlinked files
			for dir in dirs:
				dirpath = os.path.join(root, dir)
				if not os.path.exists(dirpath):
					log.debug("directory {} does not exist".format(dir))
					dirs.remove(dir)
				if IGNORE_HIDDEN and dir.startswith('.'):
					log.debug("removing hidden directory {}".format(dir))
					dirs.remove(dir)
				if IGNORE_SYMLINKS and os.path.islink(dirpath):
					log.debug("removing symlinked directory {}".format(dir))
					dirs.remove(dir)

			for file in files:
				if IGNORE_HIDDEN and file.startswith('.'):
					continue
				filepath = os.path.join(root, file)
				if not os.path.exists(filepath):
					continue
				if IGNORE_SYMLINKS and os.path.islink(filepath):
					continue
				for ignore in ignoreList:
					if fnmatch.fnmatch(filepath, ignore):
						log.debug("file {} is ignored".format(file))
						continue
				if len(filterList) == 0:
					fileList.append( File(file, root))
				else:
					for filter in filterList:
						if fnmatch.fnmatch(filepath, filter):
							fileList.append( File(file, root))

	return fileList

def generateFileDictionary(fileList):
	fileDictionary = {}
	for file in fileList:
		file.calculate()
		if file.getHash() in fileDictionary.keys():
			fileDictionary[file.getHash()].append(file)
		else:
			fileDictionary[file.getHash()] = [ file ]
	return fileDictionary

def parseArgs():
	parser = argparse.ArgumentParser()
	parser.add_argument('--directory', '-d', nargs='*', required=True)
	parser.add_argument('--ignore', '-i', nargs='*', default=[],
		help='List of file patterns to be ignored from dedup list, e.g. "--ignore *.c *.h"')
	parser.add_argument('--filter', '-f', nargs='*', default=[],
		help='List of file patterns to be included in dedup list, e.g. "--filter *.jpg *.png"')
	parser.add_argument('--verbose', '-v', action='count', default=0)
	parser.add_argument('--delete', action='store_true', default=False)
	return parser.parse_args()

def persistObject(filename, object):
	with open(filename, 'wb') as f:
		pickle.dump(object, f, pickle.HIGHEST_PROTOCOL)

def loadObject(filename):
	with open(filename, 'rb') as f:
		return pickle.load(f)

if __name__ == '__main__':
	log.basicConfig(level=log.INFO, format='%(levelname)s: %(message)s')

	args = parseArgs()
	log.info(args)

	fileList = generateFileList(directoryList=args.directory, 
		ignoreList=args.ignore, filterList=args.filter)

	log.info("{} files read".format(len(fileList)))

	if PERSIST_FILELIST:
		try:
			fileListOld = loadObject(PERSIST_FILENAME)
			for f in fileList:
				for o in fileListOld:
					f.update(o)
		except FileNotFoundError:
			pass

	fileDictionary = generateFileDictionary(fileList)

	if PERSIST_FILELIST:
		persistObject(PERSIST_FILENAME, fileList)

	for hash, files in fileDictionary.items():
		if len(files) > 1:
			print(hash + ":")
			for f in files:
				print("\t{}".format(f))
			if args.delete:
				for i in range(1,len(files)):
					log.error("Deleting file {}".format(files[i].getFilePath()))
					os.remove(files[i].getFilePath())



