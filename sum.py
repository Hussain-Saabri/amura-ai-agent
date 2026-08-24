



def maximumAdjacent(arr):
    result = []
    for i in range(len(arr)-1):
        if i == 0:
            if arr[i] > arr[i+1]:
                result.append(arr[i])
                print(result)
            else:
                result.append(arr[i+1])
                print(result)
        elif i == len(arr)-1:
            print(f"last elemtnet reached {i}")
            if arr[i] > arr[i-1]:
                result.append(arr[i])
                print(result)
            else:
                result.append(arr[i-1])
                print(result)
            return result
        else: 
            if arr[i-1] > arr[i+1]:
                result.append(arr[i-1])
                print(result)
            else:
                result.append(arr[i+1])
                print(result)
    return result




arr = [5,5]
result = maximumAdjacent(arr)
