import multiprocessing
import string
import collections
import os 

class Mapper:
    def map(self, filename):
        """
        Read a file and return a sequence of (word, occurences) values.
        """
        STOP_WORDS = set([
            'a', 'an', 'and', 'are', 'as', 'be', 'by', 'for', 'if',
            'in', 'is', 'it', 'of', 'or', 'py', 'rst', 'that', 'the',
            'to', 'with', 'rfc', 'not', 's', 'org', 'www', 'ietf', 'https', 'on'
        ])
        # Replace all punctuation with spaces.
        TR = str.maketrans({
            p: ' '
            for p in string.punctuation
        })
        print('{} reading {}'.format(multiprocessing.current_process().name, filename)) # Print the progress of the mapper

        output = [] # A sequence of (word, occurences) tuples
        with open(filename, 'rt') as f:
            for line in f:
                # Skip comment lines.
                if line.lstrip().startswith('..'): # lstrip() removes leading whitespace
                    continue 
                line = line.translate(TR)  # Strip punctuation
                for word in line.split(): # Split into words
                    word = word.lower()
                    if word.isalpha() and word not in STOP_WORDS: 
                        output.append((word, 1)) 
        return output
    

class Reducer:
    def partition(self, mapped_values):
        """
        Organize the mapped values by their key.
        Returns an unsorted sequence of tuples with a key
        and a sequence of values.
        """
        partitioned_data = collections.defaultdict(list)
        for key, value in mapped_values: 
            partitioned_data[key].append(value) 
        return partitioned_data.items()
    
    def reduce(self, input):
        """
        Convert the partitioned data for a word to a
        tuple containing the word and the number of occurences.
        """
        output = []
        
        partitioned_data = list(self.partition(input))
        for word, occurences in partitioned_data: 
            output.append((word, sum(occurences))) # Sum the occurences for each word
        return output

def map_worker(input_data, output_queue):
    """
    Process input data using a Mapper object and put the results into an output queue.
    """
    mapper = Mapper()

    for data in input_data: # for each file in input_data file list, call mapper.map
        output = mapper.map(data)
        output.sort()
        output_queue.put(output)
    
        

def reduce_worker(mapper_outputs, result_queue):
    """
    Process input data using a Reducer object and put the results into an output queue.
    """
    reducer = Reducer()  

    result = reducer.reduce(mapper_outputs)
    result_queue.put(result)

def start_mappers(filenames, reducer_queues, output_queue, number_mappers):
        """
        Start mapper processes and return a list of queues that contain the mapped values.
        """
        print('Starting mapper processes')
        mapper_processes = []
        for i in range(number_mappers):
            split_point = len(filenames) // number_mappers 
            remaining = len(filenames) % number_mappers
            if i == number_mappers - 1:
                input = filenames[i * split_point: (i + 1) * split_point + remaining] # Add the remaining files to the last mapper
            else:
                input = filenames[i * split_point: (i + 1) * split_point] # Split the filenames into chunks
            mapper = multiprocessing.Process(target=map_worker, args=(input, output_queue)) # Create a mapper process

            mapper_processes.append(mapper)

        for mapper in mapper_processes:
            mapper.start() # Start the mapper process
        
        # mapper.terminate()

        for mapper in mapper_processes:
            mapper.join() # Wait for the mapper process to finish
        

        queue_length = output_queue.qsize()
        output_queue.put(None) # Add None to the output queue to signal the end of the queue

        for item in iter(output_queue.get, None): # Iterate through the output queue
            queue_length = output_queue.qsize() # Get the length of the output queue
            hash_value = hash(queue_length) # Hash the index of the output queue
            positive_hash = hash_value % (2**64) # Ensure the hash value is non-negative
            reducer_index = positive_hash % len(reducer_queues) # Map the hash value to a specific reducer index
            reducer_queues[reducer_index] += item # Add the output to the reducer queue
            print("Added to reducer queue {}".format(reducer_index)) # Print the progress of the reducer

        new_queue = [] 
        for i, queue in enumerate(reducer_queues): 
            split_point = len(reducer_queues[0]) // len(reducer_queues) 
            remaining = len(reducer_queues[0]) % len(reducer_queues) 
            if i == len(reducer_queues)  - 1:
                input = reducer_queues[0][i * split_point: (i + 1) * split_point + remaining] 
            else:
                input = reducer_queues[0][i * split_point: (i + 1) * split_point] 
            new_queue.append(input)
        
        reducer_queues = new_queue
        for queue in reducer_queues:
            queue.append("EOF") # Add EOF to the end of each reducer queue
        
        return reducer_queues

def start_reducers(reducer_queues, result_queue, number_mappers, number_reducers):
        """
        Start reducer processes and return a list of queues that contain the reduced values.
        """
        print('Starting reducer processes')
        if all(queue[-1] != "EOF" for queue in reducer_queues): # Check if EOF is in the reducer queues
            print("Error: EOF not found in reducer queues. Mapping has not finished yet.")
            return        
        else:
            for queue in reducer_queues: 
                queue.pop() # Remove EOF from the reducer queues

        reducer_processes = []
        for i in range(number_reducers):
            input = reducer_queues[i]
            reducer = multiprocessing.Process(target=reduce_worker, args=(input, result_queue)) # Create a reducer process
            reducer_processes.append(reducer) # Add the reducer process to the reducer_processes list
        
        for reducer in reducer_processes:
            reducer.start() # Start the reducer process
        
        # reducer.terminate()  

        for reducer in reducer_processes:
            reducer.join()  # Wait for the reducer process to finish
        
        result = []
        for i in range(result_queue.qsize()):
            output = result_queue.get() 
            result += output # Add the output to the result list

        return result

def return_top20(reduced_values):
    """
    Return the top 20 words by frequency.
    """
    final_result = {}
    for word, count in reduced_values:
        if word not in final_result:
            final_result[word] = count
        else:
            final_result[word] += count 
    
    final_result_list = list(final_result.items()) 
    final_result_list.sort(key=lambda x: x[1], reverse=True) # Sort the final result list by frequency
 
    print('\nTOP 20 WORDS BY FREQUENCY\n')
    top20 = final_result_list[:20]
    longest = max(len(word) for word, count in top20)
    for word, count in top20: 
        print('{word:<{len}}: {count:5}'.format( 
            len=longest + 1,
            word=word,
            count=count)
        ) 

def main():

    filenames = []
    for r, d, f in os.walk('input/'): # Walk through the input directory

        for file in f:
            if file != '.DS_Store': # Ignore .DS_Store files
                filename = os.path.join(r, file)
                filenames.append(filename) 
    
    manager = multiprocessing.Manager() # Create a multiprocessing manager
    output_queue = manager.Queue()
    result_queue = manager.Queue() 

    number_mappers = 4
    number_reducers = 2

    reducer_input = [[]] * number_reducers
    reducer_queues = start_mappers(filenames, reducer_input, output_queue, number_reducers) # Start the mappers
    print('Mapper processes finished')

    reduced_values = start_reducers(reducer_queues, result_queue, number_mappers, number_reducers) # Start the reducers
    print('Reducer processes finished')

    return return_top20(reduced_values)
    
# Run the main function
if __name__ == "__main__":
    main()



