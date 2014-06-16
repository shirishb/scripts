#! /usr/bin/env python3.4

import sys
import argparse
import logging as log
import os
import hashlib
import fnmatch
import pickle

IGNORE_HIDDEN=True
IGNORE_SYMLINKS=True
PERSIST_FILELIST=True
PERSIST_FILENAME='dedup.filelist'

def parseArgs():
	parser = argparse.ArgumentParser()
	parser.add_argument('--directory', '-d', dest='directoryList', nargs='*', required=True)
	parser.add_argument('--include', '-i', dest='includePatternList', nargs='*', default=['*'],
		help='List of patterns which files need to match to be in dedup list, e.g. "--include *.jpg *.png"')
	parser.add_argument('--exclude', '-e', dest='excludePatternList', nargs='*', default=[],
		help='List of patterns which files should not match to be in dedup list, e.g. "--exclude *.c *.h"')
	parser.add_argument('--verbose', '-v', action='count', default=0)
	parser.add_argument('--exact', action='store_true', default=False,
		help='This option will enable exact matching by filename for a file to be considered a duplicate')
	parser.add_argument('--delete', action='store_true', default=False)
	parser.add_argument('--list', action='store_true', default=True)
	return parser.parse_args()

class File():
	def __init__(self, filename, dirpath):
		# Immutable (desired) instance variables
		self.__filename = filename
		self.__dirpath = dirpath
		# "Hash" variables
		self.__hash = None
		self.__size = None
		self.__modified_timestamp = None
		# Flag variables
		self.__marked_for_action = False

	def __str__(self):
		return "{}, {} ({} bytes)".format(self.__dirpath, self.__filename, self.__size)

	def getFileName(self):
		return self.__filename

	def getFileSize(self):
		return self.__size

	def getFilePath(self):
		return os.path.join(self.__dirpath, self.__filename)

	def getHash(self):
		return self.__hash

	def mark(self):
		self.__marked_for_action = True

	def isMarked(self):
		return self.__marked_for_action

	def updateHashFromFile(self, file):
		if self.__filename == file.__filename:
			if self.__dirpath == file.__dirpath:
				self.__hash = file.__hash
				self.__size = file.__size
				self.__modified_timestamp = file.__modified_timestamp
				# do not update self.__marked_for_action
				return True
		return False

	def calculateHash(self):
		filepath = os.path.join(self.__dirpath, self.__filename)

		# Do not recalculate if hash already exists and is unchanged
		# in both size and last modified time
		if self.__hash is not None:
			if self.__modified_timestamp == os.path.getmtime(filepath):
				if self.__size == os.path.getsize(filepath):
					return

		self.__size = os.path.getsize(filepath)
		self.__modified_timestamp = os.path.getmtime(filepath)

		# Source:
		# http://stackoverflow.com/questions/1131220/get-md5-hash-of-big-files-in-python
		md5 = hashlib.md5()
		with open(filepath,'rb') as f:
			for chunk in iter(lambda: f.read(md5.block_size * 4), b''):
				 md5.update(chunk)
		self.__hash = md5.hexdigest()


def pathMatchesPattern(path, patternList):
	for pattern in patternList:
		if fnmatch.fnmatch(path, pattern):
			return True
	return False

def pathMatchesExclusionRules(name, dirpath, excludePatternList, includePatternList):
	if IGNORE_HIDDEN and name.startswith('.'):
		return True
	path = os.path.join(dirpath, name)
	if not os.path.exists(path):
		return True
	if IGNORE_SYMLINKS and os.path.islink(path):
		return True
	if pathMatchesPattern(path, excludePatternList):
		return True
	return not pathMatchesPattern(path, includePatternList)



def generateFileList(directoryList, excludePatternList, includePatternList):
	fileList = []
	for directory in directoryList:
		for root, dirs, files in os.walk(directory, topdown=True):
			for dir in dirs:
				if pathMatchesExclusionRules(dir, root, excludePatternList, includePatternList):
					dirs.remove(dir)

			for file in files:
				if not pathMatchesExclusionRules(file, root, excludePatternList, includePatternList):
					fileList.append(File(file, root))
	return fileList

def saveFileList(fileList):
	try:
		with open(PERSIST_FILENAME, 'wb') as f:
			pickle.dump(fileList, f, pickle.HIGHEST_PROTOCOL)
	except Exception as err:
		log.error("Failed to save file list: {}".format(err))

def loadSavedFileList():
	fileList = []
	try:
		with open(PERSIST_FILENAME, 'rb') as f:
			fileList = pickle.load(f)
	except FileNotFoundError:
		pass
	except Exception as err:
		log.error("Failed to load saved file list: {}".format(err))
	return fileList

def isFileSizeIdenticalInList(fileList):
	size = None
	for file in fileList:
		if size is None:
			size = file.getFileSize()
		else:
			if size != file.getFileSize():
				return False
	return True

def isFileNameIdenticalInList(fileList):
	filename = None
	for file in fileList:
		if filename is None:
			filename = file.getFileName()
		else:
			if filename != file.getFileName():
				return False
	return True

if __name__ == '__main__':
	log.basicConfig(level=log.DEBUG, format='%(levelname)s: %(message)s')

	args = parseArgs()
	log.info(args)

	fileList = generateFileList(args.directoryList, args.excludePatternList,
		args.includePatternList)

	log.info("{} files read".format(len(fileList)))

	if PERSIST_FILELIST:
		savedFileList = loadSavedFileList()
		# Since each file is unique within a list and can only match a single
		# file in the other list -- we save some computation time by reducing
		# the size of the inner loop (savedFileList) with each successful
		# iteration of the outer loop (fileList).
		for file in fileList:
			for oldFile in savedFileList:
				if file.updateHashFromFile(oldFile):
					savedFileList.remove(oldFile)

	# Organize the file list as a dictionary keyed by the files hash, thereby
	# collecting potential duplicate files together under the same key
	fileDictionary = {}
	for file in fileList:
		file.calculateHash()
		if file.getHash() in fileDictionary.keys():
			fileDictionary[file.getHash()].append(file)
		else:
			fileDictionary[file.getHash()] = [ file ]

	# Cache file list for future use to avoid having to recompute file hashes
	if PERSIST_FILELIST:
		saveFileList(fileList)

	# Finally, iterate through the file dictionary and process user selected
	# actions on potential duplicate files
	for hash, files in fileDictionary.items():
		# More than one file per hash indicates potential duplicate files
		if len(files) > 1:
			if args.list:
				print(hash + ":")
				for f in files:
					print("\t{}".format(f))
			if args.delete:
				if not isFileSizeIdenticalInList(files):
					log.info("File size is not identical")
					break
				if args.exact and not isFileNameIdenticalInList(files):
					log.info("File name is not identical")
					break
				for i in range(1,len(files)):
					log.info("Deleting file {}".format(files[i].getFilePath()))
					os.remove(files[i].getFilePath())

