import json
import time
from hashlib import sha256

from flask import Flask, request
import requests

from app import app
from app import views


class Block:

    def __init__(self, index, content, previous_hash, timestamp=time.time(), nonce=0, hashcode=None):
        """
        Constructor of the "Block" class.
        :param index: the index of the block in the chain
        :param previous_hash: The hash of the previous block.
        :param content: Content that the block contains.
        :param timestamp: Time the block generated
        :param nonce: the proof of work of the block
        :param hashcode: the hash of the block
        """

        self.index = index
        self.content = content
        self.previous_hash = previous_hash
        self.timestamp = timestamp
        self.nonce = 0
        self.hashcode = self.compute_hash

    @property
    def compute_hash(self):
        """
        Creates the hash of the block using JSON string version
        of the block
        """
        info = {"index": self.index, "content": self.content, "previous_hash": self.previous_hash,
                "timestamp": self.timestamp, "nonce": self.nonce}
        block_string = json.dumps(info, sort_keys=True)
        return sha256(block_string.encode()).hexdigest()

    def proof_of_work(self, difficulty):
        """
        Calculates the proof of work of the block
        :return: True if the proof of work is successfully calculated, false otherwise
        """

        while not self.hashcode.startswith('0' * difficulty):
            self.nonce += 1
            self.hashcode = self.compute_hash


class BlockChain:
    difficulty = 4

    def __init__(self):
        """
        Constructs a blockchain
        """
        self.unconfirmed_data = []
        self.chain = []
        self._generate_genesis_block()

    def _generate_genesis_block(self):
        """
        Creates the first block
        :return: None
        """
        genesis_block = Block(0, [], "0")
        genesis_block.proof_of_work(BlockChain.difficulty)
        self.chain.append(genesis_block)

    @property
    def last_block(self):
        """
        Retrieves the most recent added block
        :return: the last block of the chain
        """
        return self.chain[-1]

    def add_data(self, data):
        """
        Adds a data to the list of unconfirmed data to process
        :param data: the data to be added to the block
        :return: None
        """
        self.unconfirmed_data.append(data)

    def mine(self):
        """
        Creates a block that contains the unconfirmed data and
        adds that block to the chain
        :return: None
        """
        current_last = self.last_block

        if not self.unconfirmed_data:
            return False
        new_block = Block(current_last.index + 1,
                          content=self.unconfirmed_data,
                          previous_hash=current_last.hashcode)
        new_block.proof_of_work(BlockChain.difficulty)
        self.add_block(new_block, new_block.hashcode)
        self.unconfirmed_data = []
        return self.last_block.index

    def add_block(self, block, proof):
        """
        Adds a new block to the ledger
        :param block:
        :param proof:
        :return:
        """
        previous_hash = self.last_block.hashcode

        if previous_hash != block.previous_hash:
            return False

        if not self.is_valid_proof(block, proof):
            return False

        block.hashcode = proof
        self.chain.append(block)
        return True

    @staticmethod
    def is_valid_proof(block, block_hash):
        """
        Checks if the hash is a valid hash and belongs to the ledger
        :param block:
        :param block_hash:
        :return: true if is valid hash, false otherwise
        """
        return (block_hash.startswith('0' * BlockChain.difficulty) and
                block_hash == block.compute_hash)

    @classmethod
    def chain_is_valid(cls, chain):
        """
        Checks if a given chain is valid and not tampered
        :param chain: the chain to be checked
        :return: true if the chain is valid and not tampered, false otherwise
        """
        previous_hash = "0"

        # Loop through the chain
        for block in chain:
            block_hash = block.hashcode
            # Remove the hash of the block to recompute
            # the hash again
            delattr(block, "hashcode")

            if not cls.is_valid_proof(block, block_hash) or \
                    not previous_hash != block.previous_hash:
                return False

            block.this_hash, previous_hash = block_hash, block_hash

        return True


# # Flask application
# app = Flask(__name__)

# A blockchain object
blockchain = BlockChain()

# A set of host addresses of participating members
peers = set()


@app.route("/add_block", methods=['POST'])
def verify_and_add():
    block_info = request.get_json()
    block = Block(block_info["index"],
                  block_info["content"],
                  block_info["timestamp"])

    added = blockchain.add_block(block, block_info["hashcode"])
    if not added:
        return "The block was discard my the node", 400
    else:
        return "The block has been added", 201


@app.route("/add_new_data", methods=['POST'])
def add_new_data():
    incoming_data = request.get_json()
    required_fields = ["author", "content"]
    for field in required_fields:
        if not incoming_data.get(field):
            return "Invalid data", 404

    incoming_data["timestamp"] = time.time()
    blockchain.add_data(incoming_data)
    print(incoming_data)
    return "Successfully added", 201


@app.route("/mine", methods=['GET'])
def mine_unconfirmed_data():
    result = blockchain.mine()
    if not result:
        return "No data to be added"
    else:
        # Making sure we have the longest chain before announcing to the network
        chain_length = len(blockchain.chain)
        consensus()
        if chain_length == len(blockchain.chain):
            # announce the recently mined block to the network
            announce_new_block(blockchain.last_block)
    return "Block #{} is mined".format(result)


@app.route("/chain", methods=['GET'])
def get_chain():
    """
    Gets the blockchain that has been updated up to the point the
    the method is called
    :return: a copy of the blockchain
    """
    blocks_chain = []
    for block in blockchain.chain:
        blocks_chain.append(block.__dict__)

    return json.dumps({"length": len(blocks_chain),
                       "chain": blocks_chain,
                       "peers": list(peers)})


@app.route("/pending", methods=['GET'])
def get_pending():
    """
    Gets the pending data that has not been mined
    :return: the list of data that has not been mined
    """
    return json.dumps(blockchain.unconfirmed_data)


@app.route("/register", methods=['POST'])
def register_new_peers():
    # Gets the host address of the new \node
    node_add = request.get_json()["node_address"]
    if not node_add:
        return "Invalid data", 400

    # Adds the node's address to the list of peers
    global peers
    peers.add(node_add)

    # Gives the new node a copy of the chain so it can sync
    return get_chain()


@app.route("/register_with", methods=['POST'])
def register_with_current_nodes():
    # Gets the host address of the new node
    node_add = request.get_json()["node_address"]
    if not node_add:
        return "Invalid data", 400

    data = {"node_address": request.host_url}

    response = requests.post(node_add+"/register", json=data)

    if response.status_code == 200:
        global blockchain
        global peers
        # Updates the chain and peer list
        chain_dump = response.json()["chain"]
        blockchain = create_chain_from_dump(chain_dump)
        peers.update(response.json()["peers"])
        return "Node has been successfully registered", 200

    else:
        # If somethings goes wrong, returns the content and error code
        return response.content, response.status_code

# functions for the server


def consensus():
    global blockchain

    longest_chain = None
    max_len = len(blockchain.chain)

    for node in peers:
        response = requests.get("http://{}/chain".format(node))
        node_chain = response.json()["chain"]
        length = response.json()["length"]

        if length > max_len and BlockChain.chain_is_valid(node_chain):
            longest_chain = node_chain
            max_len = length

    if longest_chain:
        blockchain = longest_chain
        return True
    else:
        return False


def create_chain_from_dump(chain_dump):
    bchain = BlockChain()
    for index, block_info in enumerate(chain_dump):
        block = Block(index, block_info["content"],
                      block_info["previous_hash"],
                      block_info["timestamp"])

        if index > 0:
            added = bchain.add_block(block, block_info["hashcode"])
            if not added:
                raise Exception("The chain dump is tampered")
        else:
            bchain.chain.append(block)
    return bchain


def announce_new_block(block):
    for peer in peers:
        url = "http://{}/add_block".format(peer)
        requests.post(url, data=json.dumps(block.__dict__, sort_keys=True))



