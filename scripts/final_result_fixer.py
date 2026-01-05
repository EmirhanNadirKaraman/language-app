with open('data/final_result.txt', 'r') as read_file: 
    with open('data/real_final_result.txt', 'w+') as write_file: 
        d = dict()
        lines = read_file.readlines()

        for line in lines: 
            first, second = line.split('\t')

            if first not in d: 
                d[first] = second.strip()
            
        for short_form, long_form in d.items(): 
            write_file.write(long_form + '\n')
            